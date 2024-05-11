## Run as an API server 

```sh
export GROQ_API_KEY='<Token>'
uvicorn main:app --reload

curl -X POST "http://localhost:8000/analyse" \
     -H "Content-Type: application/json" \
     -d '{
           "repo_url": "https://github.com/vercel/vercel",
           "ref": "main",
           "mono_path": "examples/vue"
         }'
```


## Try with as a client tool

```sh
docker run --rm -e GROQ_API_KEY='<Token>' \
            -v $(pwd)/main.py:/app/check-repo.py \
            -v $(pwd)/requirements.txt:/app/requirements.txt \
            python:3.10 sh -c "pip install -r /app/requirements.txt && python /app/check-repo.py https://github.com/vercel/vercel main --mono_path examples/vue"
```

## Result
```
{'language': 'javascript', 'framework': 'vue'}
```