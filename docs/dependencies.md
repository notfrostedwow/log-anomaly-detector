# Dependency licenses

The installed CLI has **zero third-party runtime dependencies**. It uses the Python
standard library. The optional Lambda entry point imports the AWS runtime's boto3
only when invoked in Lambda; CLI imports never initialize an SDK.

Development dependencies are pinned in `requirements-dev.txt`. cfn-lint brings most
of the transitive packages below; it is used only for offline template validation.
Installed license declarations and license-file locations were checked locally on
2026-10-15 and saved in [dependency-licenses.json](dependency-licenses.json).
This is an inventory, not a legal opinion or a vulnerability audit. Zaheer Miah
approved [MIT](../LICENSE) for original project code on 2026-10-15. That approval
does not relicense dependencies or replace their notices.

| Packages | Declared license / checked license text |
| --- | --- |
| pytest, ruff, mypy, mypy_extensions, setuptools, pip | MIT |
| cfn-lint | MIT-0 (MIT No Attribution) |
| aws-sam-translator, boto3, botocore, s3transfer | Apache-2.0 |
| annotated-types, attrs, iniconfig, jmespath, jsonschema, jsonschema-specifications | MIT |
| pluggy, pydantic, pydantic_core, PyYAML, referencing, rpds-py | MIT |
| six, typing-inspection, urllib3 | MIT |
| colorama, jsonpatch, jsonpointer, mpmath, networkx, sympy | BSD-3-Clause |
| packaging | Apache-2.0 OR BSD-2-Clause |
| python-dateutil | Apache-2.0 and historical BSD-3-Clause portions; see bundled LICENSE |
| regex | Apache-2.0 AND CNRI-Python |
| typing_extensions | PSF-2.0 |

The inventory includes the virtual environment's pip/setuptools tools. Isolated
package builds resolve the declared setuptools build requirement separately.
Upstream distributions contain additional bundled notices (notably botocore and
packaging); preserve those notices if redistributing their files. No dependency
source or wheels are checked into this repository. The resolved environment is
recorded for review; a later installation can select different transitive versions.

Regenerate the local inventory with `python tools/dependency_inventory.py` inside
the project virtual environment. Recheck licenses when upgrading dependencies.
