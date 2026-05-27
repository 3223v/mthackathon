from typing import TypedDict, Annotated, Sequence, Dict, Any
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    preferences: str
    interrupted: bool
    interrupt_info: str
    conversation_id: str
    current_skill: str
    plan_id: str
    context: Dict[str, Any]
