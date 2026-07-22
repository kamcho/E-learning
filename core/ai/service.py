from .client import OpenAIClient
from .exceptions import AITaskNotFoundError
from .tasks import EXPLAIN_ANSWER_TASK, ExplainAnswerTask


class AIService:
    """Central entry point for AI-powered tasks."""

    def __init__(self, client=None):
        self.client = client or OpenAIClient()
        self._tasks = {
            EXPLAIN_ANSWER_TASK: ExplainAnswerTask(client=self.client),
        }

    def run(self, task_name: str, **kwargs) -> dict:
        task = self._tasks.get(task_name)
        if not task:
            raise AITaskNotFoundError(f"Unknown AI task: {task_name}")
        return task.run(**kwargs)

    def list_tasks(self) -> list[str]:
        return list(self._tasks.keys())


ai_service = AIService()
