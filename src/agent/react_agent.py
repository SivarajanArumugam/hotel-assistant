import datetime

from langchain.agents import AgentExecutor, create_react_agent
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from core.config import settings
from agent.prompts import SYSTEM_PROMPT
from agent.session import format_draft_for_prompt
from tools.rag_tool import search_hotel_knowledge
from tools.reservation_tools import make_reservation_tools
from tools.session_tools import make_session_tools

_REACT_TEMPLATE = """{system}

TOOLS:
------

Assistant has access to the following tools:

{tools}

To use a tool, please use the following format:

```
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
```

When you have a response to say to the Human, or if you do not need to use a tool, you MUST use the format:

```
Thought: Do I need to use a tool? No
Final Answer: [your response here]
```

Begin!

Previous conversation history:
{chat_history}

New input: {input}
{agent_scratchpad}"""


def get_agent_executor(session_id: str, chat_history: list) -> AgentExecutor:
    session_tools = make_session_tools(session_id)
    reservation_tools = make_reservation_tools(session_id)
    all_tools = [
        search_hotel_knowledge,
        session_tools["get_today"],
        session_tools["open_booking_lookup"],
        session_tools["show_booking_summary"],
        session_tools["create_reservation"],
        session_tools["parse_date_expression"],
        session_tools["update_booking_draft"],
        reservation_tools[0],  # view_reservation (session-aware, gate-checked)
        reservation_tools[1],  # cancel_reservation (session-aware, gate-checked)
        reservation_tools[2],  # modify_reservation (session-aware, gate-checked)
    ]

    llm = ChatGroq(model=settings.llm_model, api_key=settings.groq_api_key, temperature=0.3)

    draft_state_str = format_draft_for_prompt(session_id)
    today_str = datetime.date.today().strftime("%Y-%m-%d (%A)")
    formatted_system = SYSTEM_PROMPT.format(today=today_str, draft_state=draft_state_str)

    try:
        from langchain import hub
        prompt = hub.pull("hwchase17/react-chat")
        prompt = prompt.partial(system=formatted_system)
    except Exception:
        prompt = ChatPromptTemplate.from_template(_REACT_TEMPLATE).partial(system=formatted_system)

    agent = create_react_agent(llm, all_tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=all_tools,
        max_iterations=25,
        handle_parsing_errors=True,
        verbose=False,
    )
