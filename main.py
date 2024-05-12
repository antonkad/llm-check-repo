import argparse
import sys
import shutil
import os
import asyncio
import uuid
import logging

import subprocess
from pydantic import BaseModel

from langchain_groq import ChatGroq
from fastapi import FastAPI, HTTPException, Body

app = FastAPI()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GitRepoRequest(BaseModel):
    repo_url: str
    ref: str
    commit: str | None = None
    mono_path: str | None = None

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/analyse")
async def detect_repo(request: GitRepoRequest = Body(...)):
    try:
        data = git_ls_tree_remote(request.repo_url, request.ref, request.commit, request.mono_path)
        assessment = assess_repo(data)
        return assessment
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logging.error(f"Unhandled error in detect_repo: {e}")
        raise HTTPException(status_code=400, detail=f"Error in processing the request: {str(e)}")
    
def remove_cloned_repo(repo_path: str):
    """
    Remove the cloned repository directory.

    Args:
    repo_path (str): The path to the directory to remove.
    """
    if os.path.exists(repo_path):
        try:
            shutil.rmtree(repo_path)
            logging.info(f"Removed directory {repo_path}")
        except Exception as e:
            logging.error(f"Failed to remove directory {repo_path}: {e}")
    else:
        logging.warning(f"Directory {repo_path} does not exist")

def git_ls_tree_remote(repo_url: str, ref: str, commit: str | None = None, mono_path: str | None = None):
    
    # Extract the repository name from the URL
    repo_name = repo_url.split('/')[-1].split('.')[0]
    unique_id = uuid.uuid4()
    repo_path = f"./{repo_name}_{unique_id}"  # Path where the repo is cloned
    commands_executed = []  # List to hold commands executed

    try:
       # Clone the repository into the specified directory without checking out the files, only the latest commit
        try:
            clone_command = f'git clone --no-checkout --depth 1 {repo_url} "{repo_path}" --branch {ref}'
            commands_executed.append(clone_command)
            subprocess.run(
                clone_command,
                shell=True,
                check=True,
                capture_output=True
            )

            mono_path = f"{mono_path}/" if mono_path and not mono_path.endswith("/") else mono_path
            ls_command = f'git ls-tree --full-name --name-only {commit or ref} {mono_path}'
            commands_executed.append(ls_command)
            ls_result = subprocess.run(ls_command, shell=True, cwd=repo_path, capture_output=True, text=True, check=True)

            if 'package.json' in ls_result.stdout:
                show_command = f'git show {commit or ref}:{mono_path}package.json'
                commands_executed.append(show_command)
                show_result = subprocess.run(show_command, shell=True, cwd=repo_path, capture_output=True, text=True, check=True)
                return ls_result.stdout + '\n' + show_result.stdout

            return ls_result.stdout

        except subprocess.CalledProcessError as e:
            # Log all commands executed before the error
            logging.error(f"Command executed:")
            for cmd in commands_executed:
                logging.error(f"{cmd}")
            logging.error(f"Error executing command. Last error: {e.stderr}")
            raise HTTPException(status_code=500, detail=f"Error executing command: {e.stderr}")

    finally:
        subprocess.run(f'rm -rf "{repo_path}"', shell=True)

def assess_repo(data: str):
    groq_api_key = os.getenv('GROQ_API_KEY')
    model = 'llama3-8b-8192'

    groq_chat = ChatGroq(
            groq_api_key=groq_api_key, 
            temperature=0,
            model_name=model
    )
            
    structured_llm = groq_chat.with_structured_output(
        method="json_mode"
    )
    return structured_llm.invoke(
        "You are an assistant for evaluating used language and eventual frameworks used in a given git repository. "
        "Make sure to return a JSON blob with keys 'language' and 'framework'. If the language is javascript and you are confident\n\n"
        "Here is the retrieved cmd outputs:\n " + data
    )


if __name__ == "__main__":
    if 'uvicorn' in sys.argv[0]:
        # Running as a web application
        pass
    else:
        parser = argparse.ArgumentParser(description='Clone a Git repository and list files based on a commit or ref.')
        parser.add_argument('repo_url', type=str, help='URL of the repository')
        parser.add_argument('ref', type=str, help='Branch or tag name')
        parser.add_argument('--commit', type=str, default=None, help='Commit hash (optional)')
        parser.add_argument('--mono_path', type=str, default=None, help='Path to the repository in case of a monorepo (optional)')

        args = parser.parse_args()
        request = GitRepoRequest(repo_url=args.repo_url, ref=args.ref, commit=args.commit, mono_path=args.mono_path)
        async def main():
            try:
                result = await detect_repo(request)
                print(result)
            except HTTPException as e:
                print(f"Error: {e.detail}")

        asyncio.run(main())