import dataclasses
import datetime
import re

import testing_farm.tfutil as tfutil


@dataclasses.dataclass(kw_only=True, unsafe_hash=True, frozen=True)
class FailedTestCase:
    """The FailedTestCase class represents a test from the testing-farm artifacts page"""

    test_name: str
    request_id: str
    chroot: str
    log_output_url: str
    log_output: str = None
    artifacts_url: str

    @classmethod
    def shorten_test_output(cls, log_output: str) -> str:
        """Remove cmake configure and build output"""
        log_output = re.sub(
            r"-- .*", "[... CMAKE CONFIGURE LOG SHORTENED ...]", log_output, 1
        )
        log_output = re.sub(r"-- .*\n", "", log_output)
        log_output = re.sub(
            r"\[\d+/\d+\] .*", "[... CMAKE BUILD LOG SHORTENED ...]", log_output, 1
        )
        log_output = re.sub(r"\[\d+/\d+\] .*\n", "", log_output)
        return log_output

    def render_as_markdown(self) -> str:
        return f"""
<details>
<summary>
<code>{self.test_name}</code> on <code>{self.chroot}</code> (see <a href="{self.artifacts_url}">testing-farm artifacts</a>)
</summary>

```
{self.shorten_test_output(self.log_output)}
```

</details>
"""

    @classmethod
    def render_list_as_markdown(cls, test_cases: list["FailedTestCase"]) -> str:
        if len(test_cases) == 0:
            return ""

        return f"""
{tfutil.results_html_comment()}

<h1><img src="https://github.com/fedora-llvm-team/llvm-snapshots/blob/main/media/tft-logo.png?raw=true" width="42" /> Testing-farm results are in!</h1>

<p><b>Last updated: {datetime.datetime.now().isoformat()}</b></p>

Some (if not all) results from testing-farm are in. This comment will be updated over time and is detached from the main issue comment because we want to preserve the logs entirely and not shorten them.

> [!NOTE]
> Please be aware that the testing-farm artifact links a valid for no longer than 90 days. That is why we persists the log outputs here.

> [!WARNING]
> This list is not extensive if tests have been run in the Red Hat internal testing-farm ranch and failed. For those, take a look in the "chroot" column of the build matrix above and look for failed tests that show a :lock: symbol.

<h2>Failed testing-farm test cases</h2>

{"".join([ test_case.render_as_markdown() for test_case in test_cases ])}
"""
