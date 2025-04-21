import asyncio
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import json
# Import the config file with API keys
from config import (
    OPENROUTER_API_KEY, 
    OPENROUTER_BASE_URL, OPENROUTER_REFERER, OPENROUTER_TITLE,
    LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
)
# Import the web_search function from search_utils
from search_utils import web_search

# Server parameters for both BMI and Weather services
bmi_server_params = StdioServerParameters(command="python", args=["bmi-server.py"])
weather_server_params = StdioServerParameters(command="python", args=["weather.py"])

def determine_server_params(query: str) -> tuple[StdioServerParameters, bool]:
    """Determine which server to use based on the query content using LLM."""
    prompt = (
        "Analyze this query and determine if it's related to BMI calculations, weather information, or neither. "
        "Respond with only 'bmi', 'weather', or 'general' based on the query's intent: "
        f"\"{query}\""
    )
    
    server_type = llm_client(prompt).lower().strip().replace("'", "").replace('"', '')
    print(f"LLM determined server type: {server_type}")
    
    if server_type == "weather":
        return weather_server_params, True
    elif server_type == "bmi":
        return bmi_server_params, True
    return None, False

def llm_client(message:str):
    """
    Send a message to the LLM and return the response.
    """
    # Initialize the OpenAI client using config values
    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    response = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": OPENROUTER_REFERER,
            "X-Title": OPENROUTER_TITLE,
        },
        extra_body={},
        model=LLM_MODEL,
        messages=[
            {"role":"system", "content":"You are an intelligent assistant. You will execute tasks as prompted"},
            {"role": "user", "content": message}
        ],
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE
    )
   
    # Extract and return the response content
    return response.choices[0].message.content.strip()


def get_prompt_to_identify_tool_and_arguments(query, tools):
    tools_description = "\n".join([f"- {tool.name}, {tool.description}, {tool.inputSchema} " for tool in tools])
    return (
        "You are an intelligent assistant that analyzes user queries to determine the most appropriate tool to use. \n\n"
        "Available tools:\n"
        f"{tools_description}\n\n"
        "Instructions:\n"
        "1. Analyze the semantic meaning and intent of the user's query\n"
        "2. Consider the purpose and capabilities of each available tool\n"
        "3. Select the most appropriate tool based on the query's intent, not just keywords\n"
        "4. Extract or infer the necessary arguments from the query\n\n"
        f"User's Query: {query}\n\n"
        "Response format (JSON only):\n"
        "{\n"
        '    "tool": "selected-tool-name",\n'
        '    "arguments": {\n'
        '        "parameter": "value"\n'
        "    }\n"
        "}\n"
    )


async def run(query: str):
    # Determine which server to use based on the query
    server_params, use_tool = determine_server_params(query)
    print(f"server_params: {server_params}")
    print(f"use_tool: {use_tool}")
    
    if not use_tool:
        # Handle general queries with web search
        print("Handling as general query using web search...")
        search_results = web_search(query)  # Using the imported function
        
        if search_results and not search_results.startswith("Error"):
            print("Web search results found. Generating answer with LLM...")
            prompt = f"""Based on these search results, please answer the question: "{query}"
            
Search results:
{search_results}

Provide a concise answer based on the information in these search results."""
            
            response = llm_client(prompt)
        else:
            print("No web search results or error occurred. Asking LLM directly.")
            prompt = f"Please answer this question: {query}"
            response = llm_client(prompt)
        
        print(f"\nAnswer: {response}")
        return

    # Handle BMI or Weather tool calls
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Get the list of available tools
            tools = await session.list_tools()
            prompt = get_prompt_to_identify_tool_and_arguments(query, tools.tools)
            llm_response = llm_client(prompt)
            print(f"LLM Response: {llm_response}")

            try:
                tool_call = json.loads(llm_response)
                result = await session.call_tool(tool_call["tool"], arguments=tool_call["arguments"])

                # Print the result based on the tool that was called
                if tool_call["tool"].startswith("calculate_bmi"):
                    print(f"BMI for weight {tool_call['arguments']['weight_kg']}kg and height {tool_call['arguments']['height_m']}m is {result.content[0].text}")
                elif tool_call["tool"] == "get_forecast":
                    print(f"Weather forecast:\n{result.content[0].text}")
                elif tool_call["tool"] == "get_alerts":
                    print(f"Weather alerts:\n{result.content[0].text}")
                else:
                    print(f"Result: {result.content[0].text}")
            except json.JSONDecodeError:
                print(f"Error: LLM did not return valid JSON for tool call: {llm_response}")
            except Exception as e:
                print(f"Error during tool call: {e}")


if __name__ == "__main__":
    # Example queries that demonstrate BMI, weather, and general search functionality
    queries = [
        "Calculate BMI for a person with weight 70kg and height 1.75m",
        "What's the weather forecast for NY?",
        "who is the president of the united states now?",
        "What is the capital of France?",
        "When was Apple Inc. founded?"
    ]
    
    for query in queries:
        print(f"\nProcessing query: {query}")
        asyncio.run(run(query))