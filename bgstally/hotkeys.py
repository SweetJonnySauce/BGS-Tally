import importlib
from time import sleep
from typing import Any, Callable

from bgstally.debug import Debug

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 0.25


class Hotkeys:
    """
    Minimal EDMC-Hotkeys integration for progress window build navigation.
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

        previous_action = self._create_action_with_retries(
            action_id="bgstally.progress.previous_build",
            label="Previous Build",
            callback=self._previous_build,
        )
        next_action = self._create_action_with_retries(
            action_id="bgstally.progress.next_build",
            label="Next Build",
            callback=self._next_build,
        )

        all_ok: bool = True
        for action in [previous_action, next_action]:
            if action is None:
                all_ok = False
                continue
            all_ok = self._register_action_with_retries(action) and all_ok

        return all_ok

    def _load_api(self) -> bool:
        """
        Load EDMC-Hotkeys API and Action class.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._hotkeys_api = importlib.import_module("EDMC-Hotkeys.load")
                registry_module = importlib.import_module("edmc_hotkeys.registry")
                self._action_class = getattr(registry_module, "Action")
                return True
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    Debug.logger.info("EDMC-Hotkeys not available, skipping hotkey registration")
                    Debug.logger.debug("Hotkeys load failed after retries", exc_info=e)
                    return False

                delay = self._backoff_seconds(attempt)
                Debug.logger.info(f"EDMC-Hotkeys load failed (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s")
                sleep(delay)

        return False

    def _create_action_with_retries(self, action_id: str, label: str, callback: Callable[..., Any]) -> Any | None:
        """
        Build an Action object with retry/backoff.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if self._action_class is None:
                    raise RuntimeError("Action class unavailable")

                return self._action_class(
                    id=action_id,
                    label=label,
                    plugin=self.plugin_name,
                    callback=callback,
                    thread_policy="main",
                    cardinality="single",
                )
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    Debug.logger.error(f"Failed to create hotkey action '{action_id}' after {MAX_RETRIES} attempts", exc_info=e)
                    return None

                delay = self._backoff_seconds(attempt)
                Debug.logger.info(f"Failed creating action '{action_id}' (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s")
                sleep(delay)

        return None

    def _register_action_with_retries(self, action: Any) -> bool:
        """
        Register an Action with EDMC-Hotkeys using retry/backoff.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if self._hotkeys_api is None:
                    raise RuntimeError("EDMC-Hotkeys API unavailable")

                if bool(self._hotkeys_api.register_action(action)):
                    return True

                raise RuntimeError("register_action returned False")
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    Debug.logger.error(f"Failed to register hotkey action '{action.id}' after {MAX_RETRIES} attempts", exc_info=e)
                    return False

                delay = self._backoff_seconds(attempt)
                Debug.logger.info(f"Failed registering action '{action.id}' (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s")
                sleep(delay)

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
