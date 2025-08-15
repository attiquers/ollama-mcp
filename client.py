import asyncio
from dotenv import load_dotenv
load_dotenv()

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama

import langchain
langchain.debug = True  # shows tool calls

async def main():
    client = MultiServerMCPClient({
        "math": {"command": "python", "args": ["mathserver.py"], "transport": "stdio"},
        "weather": {"url": "http://localhost:8000/mcp", "transport": "streamable_http"}
    })

    tools = await client.get_tools()
    print("MCP tools loaded:", [t.name for t in tools])

    model = ChatOllama(
        model="llama3.1",
        system_prompt="You are a helpful assistant. Always return tool outputs directly without extra reasoning."
    )
    agent = create_react_agent(model, tools)  # no unsupported kwargs


    # Math test
    math_response = await agent.ainvoke({
        "messages": [{"role": "user", "content": "what's (3 + 5) x 12?"}]
    })
    print("Math response:", math_response['messages'][-1].content)

    # Weather test (tool output is already inserted automatically)
    weather_response = await agent.ainvoke({
        "messages": [{"role": "user", "content": "what is the weather in California?"}]
    })
    print("Weather response:", weather_response['messages'][-1].content)

if __name__ == "__main__":
    asyncio.run(main())
