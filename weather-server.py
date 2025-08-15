import asyncio
from dotenv import load_dotenv
load_dotenv()

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama

import langchain
langchain.debug = True  # Verbose logging for tool calls


async def main():
    # 1️⃣ Setup MCP client with correct servers
    client = MultiServerMCPClient(
        {
            "math": {
                "command": "python",
                "args": ["./mathserver.py"],  # Use correct path
                "transport": "stdio",
            },
            "weather": {
                "url": "http://localhost:8000/mcp",  # Ensure this server is running
                "transport": "streamable_http",
            }
        }
    )

    # 2️⃣ Fetch tools from all MCP servers
    tools = await client.get_tools()
    print("MCP tools loaded:", [t.name for t in tools])

    # 3️⃣ Initialize Ollama model that supports tool-calling
    model = ChatOllama(model="llama3.1")  # Ensure this is installed locally

    # 4️⃣ Create ReAct agent with tools
    agent = create_react_agent(model, tools)

    # 5️⃣ Test math tool
    print("\n--- Running Math Prompt ---\n")
    math_response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "what's (3 + 5) x 12?"}]}
    )
    print("Math response:", math_response['messages'][-1].content)

    # 6️⃣ Test weather tool
    print("\n--- Running Weather Prompt ---\n")
    weather_response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "what is the weather in California?"}]}
    )
    print("Weather response:", weather_response['messages'][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
