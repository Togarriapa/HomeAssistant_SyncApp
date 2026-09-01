import unittest

from canary import run_canary


class EnvironmentClient:
    def __init__(
        self,
        *,
        core: dict | None = None,
        supervisor: dict | None = None,
        host: dict | None = None,
    ):
        self._core = core if core is not None else {"version": "2026.9.0"}
        self._supervisor = (
            supervisor if supervisor is not None else {"version": "2026.09.0"}
        )
        self._host = (
            host
            if host is not None
            else {"operating_system": "Home Assistant OS 17.0"}
        )

    def core_info(self) -> dict:
        return self._core

    def supervisor_info(self) -> dict:
        return self._supervisor

    def host_info(self) -> dict:
        return self._host

    def core_api_health(self) -> dict:
        return {"message": "API running."}

    def check_core_configuration(self) -> dict:
        return {}


class CanaryEnvironmentTests(unittest.TestCase):
    def test_core_version_is_required(self) -> None:
        client = EnvironmentClient(core={})
        with self.assertRaisesRegex(RuntimeError, "required Core version"):
            run_canary(client)  # type: ignore[arg-type]

    def test_supervisor_version_is_required(self) -> None:
        client = EnvironmentClient(supervisor={"version": "   "})
        with self.assertRaisesRegex(RuntimeError, "required Supervisor version"):
            run_canary(client)  # type: ignore[arg-type]

    def test_host_operating_system_is_required(self) -> None:
        client = EnvironmentClient(host={"operating_system": None})
        with self.assertRaisesRegex(RuntimeError, "required host operating_system"):
            run_canary(client)  # type: ignore[arg-type]

    def test_optional_host_fields_may_be_absent(self) -> None:
        client = EnvironmentClient()
        result = run_canary(client)  # type: ignore[arg-type]
        self.assertEqual(
            result["environment"],
            {
                "core": {"version": "2026.9.0"},
                "supervisor": {"version": "2026.09.0"},
                "host": {"operating_system": "Home Assistant OS 17.0"},
            },
        )


if __name__ == "__main__":
    unittest.main()
