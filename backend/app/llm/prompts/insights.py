SYSTEM = """You are the Insights Agent for a Lloyd's bordereaux platform. Answer analyst and
underwriter questions using ONLY the portfolio data provided. Quote specific numbers.
If the data does not contain the answer, say so plainly. 2-4 sentences."""


def portfolio_question(context: dict, question: str) -> str:
    return f"Portfolio data (JSON):\n{context}\n\nQuestion: {question}"


def file_question(context: dict, question: str) -> str:
    return f"Current bordereaux file context (JSON):\n{context}\n\nQuestion about this file: {question}"
