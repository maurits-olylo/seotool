from dataclasses import dataclass
from urllib.robotparser import RobotFileParser


@dataclass(frozen=True)
class RobotsRules:
    content: str
    source_url: str

    def allows(self, url: str, user_agent: str = "SEO-Monitor-Bot") -> bool:
        parser = RobotFileParser()
        parser.set_url(self.source_url)
        parser.parse(self.content.splitlines())
        return parser.can_fetch(user_agent, url)

    def sitemaps(self) -> tuple[str, ...]:
        values: list[str] = []
        for line in self.content.splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() == "sitemap" and value.strip():
                values.append(value.strip())
        return tuple(values)
