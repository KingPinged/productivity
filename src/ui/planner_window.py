import threading

import webview


class PlannerWindow:
    def __init__(self, server_url: str, auth_token: str):
        self._server_url = server_url
        self._auth_token = auth_token
        self._window: webview.Window | None = None
        self._thread: threading.Thread | None = None

    def show(self) -> None:
        if self._window is not None:
            try:
                self._window.show()
                return
            except Exception:
                self._window = None

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._window = webview.create_window(
            title="Productivity Planner",
            url=self._server_url,
            width=1200,
            height=800,
            min_size=(800, 600),
            text_select=True,
        )
        webview.start()

    def destroy(self) -> None:
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
