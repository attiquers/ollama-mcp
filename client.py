import asyncio
from dotenv import load_dotenv
load_dotenv()

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama

async def main():
    # MCP client setup
    client = MultiServerMCPClient({
        "math": {"command": "python", "args": ["mathserver.py"], "transport": "stdio"},
        "weather": {"url": "http://localhost:8000/mcp", "transport": "streamable_http"}
    })

    tools = await client.get_tools()

    # Ollama model
    model = ChatOllama(
        model="qwen3:1.7b",
        system_prompt=(
            "You are a helpful assistant with access to external tools. "
            "When a user asks a question, determine if a tool can answer it. "
            "If a tool is needed, call the appropriate tool with correct parameters. "
            "Once the tool returns its result, restate that result in clear, concise, natural language for the user. "
            "Do NOT invent any information or add extra facts — only use the tool outputs. "
            "Always make the answer easy to understand and friendly for humans. "
            "If no tool is needed, answer directly but clearly."
        )

    )

    agent = create_react_agent(model, tools)

    # Simple function to handle QA
    async def ask(question: str):
        response = await agent.ainvoke({"messages": [{"role": "user", "content": question}]})
        # Just print the last AI response
        print(f"Q: {question}\nA: {response['messages'][-1].content}\n")

    # Tests
    await ask("what's (3 + 5) x 12?")
    await ask("what is the weather in California?")

if __name__ == "__main__":
    asyncio.run(main())
