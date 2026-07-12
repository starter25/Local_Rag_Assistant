import os

import uvicorn


def main():
    host = os.getenv("LOCAL_RAG_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("LOCAL_RAG_SERVER_PORT", "8000"))
    log_level = os.getenv("LOCAL_RAG_SERVER_LOG_LEVEL", "warning")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
