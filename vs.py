import os
import uvicorn


def main() -> None:
    uvicorn.run(
        "src.web.app:app",
        host=os.environ.get("VUESCAN_HOST", "127.0.0.1"),
        port=int(os.environ.get("VUESCAN_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    main()
