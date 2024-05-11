import argparse
import sys
import shutil
import os
import asyncio
import uuid

import subprocess
from pydantic import BaseModel

from langchain_groq import ChatGroq
from fastapi import FastAPI, HTTPException, Body

app = FastAPI()

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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
def remove_cloned_repo(repo_path: str):
    """
    Remove the cloned repository directory.

    Args:
    repo_path (str): The path to the directory to remove.
    """
    # Ensure the directory exists before attempting to remove it
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
        print(f"Removed directory {repo_path}")
    else:
        print(f"Directory {repo_path} does not exist")

def git_ls_tree_remote(repo_url: str, ref: str, commit: str | None = None, mono_path: str | None = None):
    # Extract the repository name from the URL
    repo_name = repo_url.split('/')[-1].split('.')[0]
    unique_id = uuid.uuid4()
    repo_path = f"./{repo_name}_{unique_id}"  # Path where the repo is cloned

    try:
        # Extract the repository name from the URL
        repo_name = repo_url.split('/')[-1].split('.')[0]

       # Clone the repository into the specified directory without checking out the files, only the latest commit
        clone_process = subprocess.run(
            f'git clone --no-checkout --depth 1 {repo_url} "{repo_path}"',
            shell=True,
            capture_output=True
        )

        if clone_process.returncode != 0:
            raise Exception("Error cloning repository: " + clone_process.stderr.decode())

        cd_process = subprocess.run(f'cd {repo_path}', shell=True, capture_output=True, text=True)

        if cd_process.returncode != 0:
            raise Exception("Error listing files: " + cd_process.stderr)
        
        if mono_path:
            if not mono_path.endswith("/"):
                mono_path += "/"

        # List the files based on commit or ref
        result = subprocess.run(f'git ls-tree --full-name --name-only {commit or ref} {mono_path}', shell=True, cwd=repo_path, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception("Error listing files: " + result.stderr)

        # Check if package.json exists in the output
        if 'package.json' in result.stdout:
            # Execute git show <ref or commit>:package.json
            show_process = subprocess.run(f'git show {commit or ref}:{mono_path}package.json', shell=True, cwd=repo_path, capture_output=True, text=True)
            if show_process.returncode != 0:
                raise Exception("Error listing files: " + show_process.stderr)
            else:
                return result.stdout + '\n' + show_process.stdout

        else:
            return result.stdout
    finally:
        remove_cloned_repo(repo_path)

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