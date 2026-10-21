"""Standalone worker for Azure Service Bus.  Run:  python -m app.workers.worker"""
import json

from app.core.config import get_settings
from app.db.session import init_db
from app.utils.logging import configure_logging, get_logger
from app.workers.jobs import execute

log = get_logger("worker")


def main():
    s = get_settings()
    configure_logging(s.log_level)
    init_db()
    from azure.servicebus import ServiceBusClient
    if s.servicebus_connection_string:
        client = ServiceBusClient.from_connection_string(s.servicebus_connection_string)
    else:
        from azure.identity import DefaultAzureCredential
        client = ServiceBusClient(s.servicebus_namespace, credential=DefaultAzureCredential())
    log.info(f"worker listening on {s.servicebus_queue}")
    with client, client.get_queue_receiver(s.servicebus_queue, max_wait_time=30) as receiver:
        while True:
            for msg in receiver.receive_messages(max_message_count=5, max_wait_time=30):
                job = json.loads(str(msg))
                if job.pop("password_ref", False):
                    from app.security.vault import get_vault
                    key = f"__job__{job.get('file_id')}"
                    job["password"] = get_vault().get(key)
                    get_vault().delete(key)
                execute(job)
                receiver.complete_message(msg)


if __name__ == "__main__":
    main()
