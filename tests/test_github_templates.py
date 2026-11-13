"""
Created on 2026-11-13

@author: danielviladrich
"""

import glob
from typing import Dict, Tuple

from basemkit.basetest import Basetest


class TestGithubTemplates(Basetest):
    """
    Test the issue and pull request templates in .github
    """

    def read_issue_templates(self) -> Dict[str, Tuple[Dict[str, str], str]]:
        """
        Read every issue template.

        The front matter only holds flat `key: value` lines, so it is read
        without a YAML parser.

        Returns:
            Dict[str, Tuple[Dict[str, str], str]]: the front matter fields and
            the body of each template, by path
        """
        templates = {}
        for path in sorted(glob.glob(".github/ISSUE_TEMPLATE/*.md")):
            with open(path, encoding="utf-8") as template_file:
                _, front_matter, body = template_file.read().split("---\n", 2)
            fields = {}
            for line in front_matter.splitlines():
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip().strip("'\"")
            templates[path] = (fields, body)
        return templates

    def test_issue_templates_have_front_matter(self):
        """
        test that every issue template has the name and about fields GitHub
        needs to offer it when a new issue is opened
        """
        templates = self.read_issue_templates()
        self.assertEqual(3, len(templates))
        for path, (fields, _) in templates.items():
            for key in ("name", "about"):
                self.assertTrue(fields.get(key), f"{path}: {key} missing")

    def test_issue_templates_ask_for_acceptance_criteria(self):
        """
        test that the standard and the epic template ask for acceptance criteria
        """
        templates = self.read_issue_templates()
        for path in (
            ".github/ISSUE_TEMPLATE/KGI_standard_issue.md",
            ".github/ISSUE_TEMPLATE/KGI_epic.md",
        ):
            _, body = templates[path]
            self.assertIn("acceptance criteria", body.lower().replace("-", " "), path)

    def test_pull_request_template_links_an_issue(self):
        """
        test that the pull request template has the line that closes the
        linked issue when the pull request is merged
        """
        with open(
            ".github/pull_request_template.md", encoding="utf-8"
        ) as template_file:
            lines = template_file.read().splitlines()
        self.assertIn("Closes #", lines)
