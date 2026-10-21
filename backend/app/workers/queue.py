"""Job queue abstraction.
  inprocess  : thread pool inside the API container (local dev, small volumes)
  servicebus : Azure Service Bus queue; run `python -m app.workers.worker` as a
               separate Container App that scales on queue length (KEDA)."""
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.core.config import get_settings


class InProcessQueue:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bdx-job")

    def enqueue(self, job: dict) -> None:
        from app.workers.jobs import execute
        self.pool.submit(execute, job)


class SyncQueue:
    """Runs the job inline - deterministic for tests and step-through debugging."""

    def enqueue(self, job: dict) -> None:
        from app.workers.jobs import execute
        execute(job)


class ServiceBusQueue:
    def __init__(self):
        from azure.servicebus import ServiceBusClient
        s = get_settings()
        if s.servicebus_connection_string:
            self.client = ServiceBusClient.from_connection_string(s.servicebus_connection_string)
        else:
            from azure.identity import DefaultAzureCredential
            self.client = ServiceBusClient(s.servicebus_namespace, credential=DefaultAzureCredential())
        self.queue = s.servicebus_queue

    def enqueue(self, job: dict) -> None:
        from azure.servicebus import ServiceBusMessage
        safe = {k: v for k, v in job.items() if k != "password"}   # never put passwords on the bus
        if job.get("password"):
            from app.security.vault import get_vault
            # one-shot: stored in the vault under a job key, read by the worker
            safe["password_ref"] = True
            get_vault().set(f"__job__{job.get('file_id')}", job["password"])
        with self.client.get_queue_sender(self.queue) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(safe)))


@lru_cache
def get_queue():
    backend = get_settings().queue_backend
    if backend == "servicebus":
        return ServiceBusQueue()
    return SyncQueue() if backend == "sync" else InProcessQueue()
