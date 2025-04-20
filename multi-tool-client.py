import asyncio
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
# Import stdio client
from mcp.client.stdio import stdio_client
import os
import json
import aiohttp # <-- Add this import
import urllib.parse # <-- Add this import


class HttpClientParameters: # Placeholder <-- Keeping this ONLY as a type marker for determine_server_params
    def __init__(self, url):
        self.url = url
        # print("WARNING: Using placeholder HttpClientParameters. HTTP client functionality is disabled.") # No longer needed

# def http_client(params): # Placeholder <-- Removed placeholder function
#     print("ERROR: HTTP client is not configured. Cannot connect.")
#     # Return a dummy async context manager that does nothing or raises error
#     class DummyHttpContext:
#         async def __aenter__(self):
#             raise NotImplementedError("HTTP client import failed or is not configured.")
#         async def __aexit__(self, exc_type, exc_val, exc_tb):
#             pass
#     return DummyHttpContext()

bmi_server_params = StdioServerParameters(command="python", args=["bmi-server.py"])
weather_server_params = StdioServerParameters(command="python", args=["weather.py"])

# Update the URL to point back to the DuckDuckGo search server
# !!! Verify this URL and the tool name/arguments used in the 'run' function below !!!
# Note: The URL here is now just informational, as we call the DDG API directly.
search_server_params = HttpClientParameters(url="https://api.duckduckgo.com/") # URL updated for clarity

def determine_server_params(query: str) -> tuple[StdioServerParameters | HttpClientParameters | None, bool]:
    """Determine which server to use based on the query content using LLM."""
    prompt = (
        "Analyze this query and determine if it's related to BMI calculations, weather information, web search, or general knowledge. "
        "Respond with only 'bmi', 'weather', 'search', or 'general' based on the query's intent: " # Updated prompt slightly
        f"\"{query}\""
    )

    server_type = llm_client(prompt).lower().strip().replace("'", "").replace('"', '')
    print(f"LLM determined server type: {server_type}") # Added print for debugging

    if server_type == "weather":
        return weather_server_params, True
    elif server_type == "bmi":
        return bmi_server_params, True
    # Treat 'search' and 'general' as needing web search fallback
    elif server_type in ["search", "general"]:
         # Return search params, but indicate False for direct tool use initially
         # We handle this case specifically in the 'run' function's 'else' block
        return search_server_params, False
    return None, False # Should ideally not be reached if LLM returns one of the expected types

def llm_client(message:str):
    """
    Send a message to the LLM and return the response.
    """
    # Initialize the OpenAI client

    client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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", # Replace with your actual API key or load from env
    )

    response = client.chat.completions.create(
    extra_headers={
    "HTTP-Referer": "testMcp", # Optional. Site URL for rankings on openrouter.ai.
    "X-Title": "testMcp", # Optional. Site title for rankings on openrouter.ai.
    },
     extra_body={},
     model="openai/gpt-4o-mini",
      messages=[{"role":"system",
                    "content":"You are an intelligent assistant. You will execute tasks as prompted"}, # Fixed missing comma
                    {"role": "user", "content": message}], # Fixed role structure
        max_tokens=250,
        temperature=0.2

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
    print(f"Selected server_params type: {type(server_params)}") # Changed print for clarity
    print(f"Use tool directly: {use_tool}")

    if use_tool and isinstance(server_params, StdioServerParameters):
        # Handle BMI or Weather tool calls via stdio
        print(f"Connecting to stdio server: {' '.join([server_params.command] + server_params.args)}...")
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                prompt = get_prompt_to_identify_tool_and_arguments(query, tools.tools)
                llm_response = llm_client(prompt)
                print(f"LLM Tool Identification Response: {llm_response}")
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
                    print(f"Error during BMI/Weather tool call: {e}")
        return # Exit after handling BMI/Weather

    # Check instance against the HttpClientParameters placeholder type marker
    elif not use_tool and isinstance(server_params, HttpClientParameters):
        # Handle general queries: Use DuckDuckGo Instant Answer API directly
        print("Handling as general query using DuckDuckGo Instant Answer API...")
        final_answer = f"Could not answer the query: '{query}'" # Default answer
        # URL-encode the query string
        encoded_query = urllib.parse.quote_plus(query)
        ddg_api_url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&pretty=1" # Use encoded query

        try:
            async with aiohttp.ClientSession() as session:
                # Add headers to mimic a browser request, which might help with DDG API behavior
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
                async with session.get(ddg_api_url, headers=headers) as response: # Added headers
                    response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                    # Allow decoding JSON even if content type is not application/json
                    data = await response.json(content_type=None) # <-- Modified this line

                    # Try to get an Instant Answer from primary fields
                    instant_answer = data.get("AbstractText") or data.get("Answer")

                    # If no answer yet, check RelatedTopics
                    if not instant_answer:
                        related_topics = data.get("RelatedTopics", [])
                        if isinstance(related_topics, list):
                            for topic in related_topics:
                                # Check if the topic itself has text or if it contains sub-topics with text
                                topic_text = topic.get("Text")
                                if topic_text:
                                    instant_answer = topic_text
                                    break # Use the first relevant text found
                                # Sometimes the answer is nested within a 'Topics' key inside RelatedTopics
                                nested_topics = topic.get("Topics")
                                if isinstance(nested_topics, list):
                                     for nested_topic in nested_topics:
                                         nested_text = nested_topic.get("Text")
                                         if nested_text:
                                             instant_answer = nested_text
                                             break # Use the first relevant text found
                                if instant_answer: # Break outer loop if answer found in nested topics
                                    break


                    if instant_answer:
                        print(f"\nDuckDuckGo Answer (from AbstractText, Answer, or RelatedTopics):\n{instant_answer}") # Updated print message
                        final_answer = instant_answer
                    else:
                        # If still no answer, print the full response and fall back to LLM
                        print("No DuckDuckGo answer found in AbstractText, Answer, or RelatedTopics.") # Updated print message
                        print(f"Full DDG Response: {json.dumps(data, indent=2)}")
                        print("Asking LLM directly.")
                        prompt = f"Please answer this question: {query}"
                        response_llm = llm_client(prompt)
                        final_answer = response_llm

        except aiohttp.ClientError as e:
            print(f"Error during DuckDuckGo API call: {e}")
            print("Falling back to asking LLM directly.")
            prompt = f"Please answer this question: {query}"
            response_llm = llm_client(prompt)
            final_answer = response_llm
        except Exception as e: # General exception handler remains
            print(f"An unexpected error occurred: {e}")
            print("Falling back to asking LLM directly.")
            # Fallback: Ask LLM the original question directly if search fails
            prompt = f"Please answer this question: {query}"
            response_llm = llm_client(prompt)
            final_answer = response_llm

        print(f"\nAnswer: {final_answer}")
        return # Exit after handling general query/search

    else:
        # Case where server_params is None or type mismatch
        print("Could not determine appropriate server or action for the query. Asking LLM directly.")
        prompt = f"Please answer this question: {query}"
        response = llm_client(prompt)
        print(f"\nAnswer: {response}")
        return


if __name__ == "__main__":
    # Example queries that demonstrate BMI, weather, and search functionality
    queries = [
        "Calculate BMI for a person with weight 70kg and height 1.75m",
        "What's the weather forecast for NY?",
        "who is the president of the united states now?",
        "What is the capital of France?",
        "Are there any weather alerts for London?" # <-- Added a new query for weather alerts
    ]

    for query in queries:
        print(f"\nProcessing query: {query}")
        asyncio.run(run(query))