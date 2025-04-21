from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio
import uvicorn
import sys
import os
import importlib.util

# Add the current directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the run function from the module with hyphens in the name
spec = importlib.util.spec_from_file_location(
    "multi_tool_search_client", 
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "multi_tool_search_client.py")
)
multi_tool_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(multi_tool_module)
run = multi_tool_module.run

app = FastAPI(title="Multi-Tool Search API", 
              description="API for querying BMI, weather, and web search tools")

class Query(BaseModel):
    question: str

class Answer(BaseModel):
    answer: str

@app.post("/query", response_model=Answer)
async def process_query(query: Query):
    """
    Process a query and return the answer from the appropriate tool
    (BMI calculator, weather service, or web search)
    """
    try:
        # Create a simple queue to get the result from the run function
        result_queue = asyncio.Queue()
        
        # Define a wrapper function that puts the result in the queue
        async def run_and_capture(question):
            # Capture stdout to get the answer
            import io
            import sys
            from contextlib import redirect_stdout
            
            f = io.StringIO()
            with redirect_stdout(f):
                await run(question)
            
            output = f.getvalue()
            
            # Extract the answer from the output
            # The answer is after the line that starts with "Answer: "
            lines = output.split('\n')
            for i, line in enumerate(lines):
                if line.startswith("Answer:"):
                    answer = line[8:].strip()  # Remove "Answer: " prefix
                    await result_queue.put(answer)
                    return
            
            # If we didn't find an answer line, return the whole output
            await result_queue.put(output)
        
        # Run the query processing in a task
        asyncio.create_task(run_and_capture(query.question))
        
        # Wait for the result
        answer = await result_queue.get()
        
        return Answer(answer=answer)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.get("/")
async def root():
    """
    Root endpoint that provides basic information about the API
    """
    return {
        "message": "Welcome to the Multi-Tool Search API",
        "usage": "Send a POST request to /query with a JSON body containing a 'question' field"
    }

if __name__ == "__main__":
    # Run the API server
    uvicorn.run(app, host="0.0.0.0", port=8000)