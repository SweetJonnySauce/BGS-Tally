from time import sleep
from typing import Any, Callable

from bgstally.debug import Debug

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 0.25


class Hotkeys:
    """
    Minimal EDMCHotkeys integration
    """
    def __init__(self, bgstally) -> None:
        self.bgstally = bgstally
        self.plugin_name: str = bgstally.plugin_name
        self._hotkeys_api: Any = None
        self._action_class: type | None = None

    def initialize(self) -> bool:
        """
        Register all hotkey actions.
        """
        if not self._load_api():
            return False

        previous_ok = self._register_action(
            action_id="bgstally.progress.previous_build",
            label="Previous Build",
            callback=self._previous_build,
            thread_policy="main",
            cardinality="single"
        )
        next_ok = self._register_action(
            action_id="bgstally.progress.next_build",
            label="Next Build",
            callback=self._next_build,
            thread_policy="main",
            cardinality="single"
        )

        return previous_ok and next_ok

    def _load_api(self) -> bool:
        """
        Load EDMCHotkeys API and Action class.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                import EDMCHotkeys as hotkeys_api
                from edmc_hotkeys.registry import Action

                self._hotkeys_api = hotkeys_api
                self._action_class = Action
                return True
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    Debug.logger.info("EDMCHotkeys not available, skipping hotkey registration")
                    Debug.logger.debug("Hotkeys load failed after retries", exc_info=e)
                    return False

                delay = self._backoff_seconds(attempt)
                Debug.logger.info(f"EDMCHotkeys load failed (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s")
                sleep(delay)

        return False

    def _register_action(
        self,
        action_id: str,
        label: str,
        callback: Callable[..., Any],
        thread_policy: str = "main",
        cardinality: str = "single",
    ) -> bool:
        """
        Build and register an Action with EDMCHotkeys.
        """
        try:
            if self._action_class is None:
                raise RuntimeError("Action class unavailable")
            if self._hotkeys_api is None:
                raise RuntimeError("EDMCHotkeys API unavailable")

            action = self._action_class(
                id=action_id,
                label=label,
                plugin=self.plugin_name,
                callback=callback,
                thread_policy=thread_policy,
                cardinality=cardinality,
            )

            if bool(self._hotkeys_api.register_action(action)):
                return True
            raise RuntimeError("register_action returned False")
        except Exception as e:
            Debug.logger.error(f"Failed to register hotkey action '{action_id}'", exc_info=e)
            return False

    def _previous_build(self, *, payload=None, source: str = "hotkey", hotkey: str | None = None) -> bool:
        del payload, source, hotkey
        return self._trigger_progress_event("prev")

    def _next_build(self, *, payload=None, source: str = "hotkey", hotkey: str | None = None) -> bool:
        del payload, source, hotkey
        return self._trigger_progress_event("next")

    def _trigger_progress_event(self, event_name: str) -> bool:
        """
        Trigger the same ProgressWindow event handlers as the UI arrow buttons.
        """
        try:
            window_progress = getattr(getattr(self.bgstally, "ui", None), "window_progress", None)
            if window_progress is None:
                return False
            if getattr(window_progress, "colonisation", None) is None:
                return False
            window_progress.event(event_name)
            return True
        except Exception as e:
            Debug.logger.error(f"Hotkey action failed for '{event_name}'", exc_info=e)
            return False

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        """
        Exponential backoff (0-based exponent from attempt 1).
        """
        return BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
