#!/usr/bin/env python3
"""Cute assistant face display powered by PyGame.

The app reads a JSON state file (default: data/demo_state.json) and
renders a pastel assistant face that reflects the current conversation
phase plus the latest user / assistant lines.
"""
from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import pygame
import yaml

BASE_DIR = Path(__file__).parent
DEFAULT_CONFIG = BASE_DIR / "config.yaml"

PHASES = ("idle", "listening", "thinking", "speaking")


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    lv = len(value)
    if lv == 6:
        return tuple(int(value[i : i + 2], 16) for i in range(0, 6, 2))  # type: ignore[return-value]
    raise ValueError(f"Unsupported color: {value}")


@dataclass
class AssistantSnapshot:
    phase: str = "idle"
    user_text: str = "No message yet"
    assistant_text: str = "Zero is on standby"
    last_update: str = ""

    def normalized_phase(self) -> str:
        return self.phase if self.phase in PHASES else "idle"


class JsonStateFeed:
    """Watch a JSON file for changes and expose the latest state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.last_mtime = 0.0
        self.snapshot = AssistantSnapshot()

    def poll(self) -> AssistantSnapshot:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return self.snapshot

        if stat.st_mtime > self.last_mtime:
            try:
                with self.path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (json.JSONDecodeError, OSError):
                return self.snapshot

            self.snapshot = AssistantSnapshot(
                phase=str(payload.get("phase", "idle")),
                user_text=str(payload.get("userText", "")),
                assistant_text=str(payload.get("assistantText", "")),
                last_update=str(payload.get("lastUpdate", "")),
            )
            self.last_mtime = stat.st_mtime

        return self.snapshot


class CuteFaceRenderer:
    def __init__(self, screen: pygame.Surface, cfg: Dict) -> None:
        self.screen = screen
        self.cfg = cfg
        self.center = (screen.get_width() // 2, screen.get_height() // 2 + 30)
        self.radius = cfg["assets"].get("face_radius", 200)
        self.outline = cfg["assets"].get("face_outline_width", 16)
        self.eye_radius = cfg["assets"].get("eye_radius", 18)
        self.mouth_width = cfg["assets"].get("mouth_width", 90)
        self.mouth_height = cfg["assets"].get("mouth_height", 32)
        self.blink_interval = float(cfg["assets"].get("blink_interval", 4.0))
        self.ear_width = cfg["assets"].get("ear_width", 140)
        self.ear_height = cfg["assets"].get("ear_height", 260)
        self.inner_ear_color = tuple(cfg["assets"].get("inner_ear_rgb", (255, 170, 200)))
        self.outline_color = tuple(cfg["assets"].get("outline_rgb", (70, 48, 40)))
        self.cheek_color = tuple(cfg["assets"].get("cheek_rgb", (255, 140, 190)))
        self.body_rect: pygame.Rect | None = None
        self.font_large = pygame.font.SysFont("Arial Rounded MT Bold", 42)
        self.font_medium = pygame.font.SysFont("Noto Sans CJK TC", 28)
        self.font_small = pygame.font.SysFont("Noto Sans CJK TC", 22)

    def draw(self, snapshot: AssistantSnapshot, colors: Dict[str, Tuple[int, int, int]], tick: float) -> None:
        phase = snapshot.normalized_phase()
        face_color = colors.get(phase, colors["idle"])
        bg = colors["background"]
        self.screen.fill(bg)

        # Body and feet (under head)
        self._draw_body(face_color)
        self._draw_tail()
        self._draw_feet()

        # Bunny ears + head
        attentive = phase == "listening"
        self._draw_ears(face_color, attentive)
        self._draw_face(face_color)

        # Eyes + blush
        self._draw_eyes(phase, tick)

        # Nose + mouth animation
        self._draw_nose()
        self._draw_mouth(phase, tick)

        # Status badge + clock
        self._draw_status_badge(phase, colors)
        self._draw_clock(colors)

    def _draw_eyes(self, phase: str, tick: float) -> None:
        blink_phase = (tick % self.blink_interval) / self.blink_interval
        eye_open = 1.0
        if 0.6 <= blink_phase < 0.75:
            eye_open = max(0.1, 1 - (blink_phase - 0.6) * 6)
        elif 0.75 <= blink_phase < 0.85:
            eye_open = 0.1
        elif 0.85 <= blink_phase < 0.95:
            eye_open = max(0.1, (blink_phase - 0.85) * 5)

        if phase == "listening":
            eye_open = min(1.2, eye_open + 0.2)

        offset_x = self.radius * 0.45
        eye_y = self.center[1] - int(self.radius * 0.25)
        for direction in (-1, 1):
            center_x = int(self.center[0] + direction * offset_x)
            pygame.draw.circle(
                self.screen,
                self.outline_color,
                (center_x, eye_y),
                int(self.eye_radius * eye_open),
            )
            blush_rect = pygame.Rect(0, 0, 48, 18)
            blush_rect.center = (center_x, eye_y + 55)
            pygame.draw.ellipse(self.screen, self.cheek_color, blush_rect)

    def _draw_nose(self) -> None:
        nose_center = (self.center[0], self.center[1] + 5)
        pygame.draw.circle(self.screen, (255, 184, 196), nose_center, 8)

    def _draw_mouth(self, phase: str, tick: float) -> None:
        mouth_y = self.center[1] + 22
        if phase == "speaking":
            anim = (math.sin(tick * 6.0) + 1) * 0.5
            open_depth = 6 + anim * 18
            width = 40 + anim * 10
            points = [
                (self.center[0] - width, mouth_y),
                (self.center[0] - width * 0.4, mouth_y + open_depth),
                (self.center[0], mouth_y + open_depth * 0.6),
                (self.center[0] + width * 0.4, mouth_y + open_depth),
                (self.center[0] + width, mouth_y),
            ]
            pygame.draw.lines(self.screen, self.outline_color, False, points, 6)
            inner_height = max(4, open_depth - 6)
            mouth_rect = pygame.Rect(0, 0, width * 1.4, inner_height)
            mouth_rect.center = (self.center[0], mouth_y + open_depth * 0.6)
            pygame.draw.ellipse(self.screen, (200, 80, 90), mouth_rect)
        else:
            mouth_points = [
                (self.center[0] - 40, mouth_y),
                (self.center[0] - 15, mouth_y + 18),
                (self.center[0], mouth_y),
                (self.center[0] + 15, mouth_y + 18),
                (self.center[0] + 40, mouth_y),
            ]
            stroke = 6 if phase != "listening" else 7
            pygame.draw.lines(self.screen, self.outline_color, False, mouth_points, stroke)

    def _draw_face(self, face_color: Tuple[int, int, int]) -> None:
        face_rect = pygame.Rect(0, 0, self.radius * 2, int(self.radius * 1.4))
        face_rect.center = self.center
        pygame.draw.ellipse(self.screen, face_color, face_rect)
        pygame.draw.ellipse(self.screen, self.outline_color, face_rect, self.outline)

    def _draw_ears(self, face_color: Tuple[int, int, int], attentive: bool) -> None:
        left_angle = -6 if attentive else -12
        right_angle = 20 if attentive else 12
        y_shift = -self.radius * (1.05 if attentive else 1.15)
        self._draw_single_ear(face_color, angle=left_angle, offset=(-self.radius * 0.4, y_shift))
        self._draw_single_ear(face_color, angle=right_angle, offset=(self.radius * 0.35, y_shift + 10))

    def _draw_single_ear(self, face_color: Tuple[int, int, int], angle: float, offset: Tuple[float, float]) -> None:
        surface = pygame.Surface((self.ear_width, self.ear_height), pygame.SRCALPHA)
        outer_rect = surface.get_rect()
        pygame.draw.ellipse(surface, self.outline_color, outer_rect)
        inner_white = outer_rect.inflate(-self.outline * 2, -self.outline * 2)
        pygame.draw.ellipse(surface, face_color, inner_white)
        pink_rect = inner_white.inflate(-self.ear_width * 0.4, -self.ear_height * 0.4)
        pygame.draw.ellipse(surface, self.inner_ear_color, pink_rect)
        rotated = pygame.transform.rotate(surface, angle)
        rect = rotated.get_rect(center=(self.center[0] + offset[0], self.center[1] + offset[1]))
        self.screen.blit(rotated, rect)

    def _draw_body(self, face_color: Tuple[int, int, int]) -> None:
        body_rect = pygame.Rect(0, 0, self.radius * 1.3, self.radius * 0.85)
        body_rect.center = (self.center[0], self.center[1] + int(self.radius * 1.0))
        pygame.draw.ellipse(self.screen, face_color, body_rect)
        pygame.draw.ellipse(self.screen, self.outline_color, body_rect, self.outline)
        self.body_rect = body_rect

    def _draw_tail(self) -> None:
        pass

    def _draw_feet(self) -> None:
        if not self.body_rect:
            return
        body_rect = self.body_rect
        foot_height = body_rect.height * 0.45
        foot_width = body_rect.width * 0.25
        base_y = body_rect.bottom - 5
        for direction in (-1, 1):
            center_x = self.center[0] + direction * body_rect.width * 0.2
            foot_rect = pygame.Rect(0, 0, foot_width, foot_height)
            foot_rect.midtop = (center_x, base_y - foot_height)
            pygame.draw.lines(
                self.screen,
                self.outline_color,
                False,
                [
                    (foot_rect.left, foot_rect.top + 5),
                    (foot_rect.left, foot_rect.bottom - 5),
                    (foot_rect.centerx, foot_rect.bottom),
                    (foot_rect.right, foot_rect.bottom - 5),
                    (foot_rect.right, foot_rect.top + 5),
                ],
                max(4, self.outline - 4),
            )

    def _draw_status_badge(self, phase: str, colors: Dict[str, Tuple[int, int, int]]) -> None:
        labels = {
            "idle": "待命",
            "listening": "傾聽中",
            "thinking": "思考中",
            "speaking": "說話中",
        }
        text = labels.get(phase, "待命")
        surface = self.font_small.render(text, True, colors["background"])
        padding = pygame.Rect(0, 0, surface.get_width() + 24, surface.get_height() + 12)
        padding.topright = (self.screen.get_width() - 32, 32)
        pygame.draw.rect(self.screen, colors[phase if phase in colors else "idle"], padding, border_radius=18)
        self.screen.blit(surface, surface.get_rect(center=padding.center))

    def _draw_clock(self, colors: Dict[str, Tuple[int, int, int]]) -> None:
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        ts_surface = self.font_small.render(now_text, True, colors["text_secondary"])
        self.screen.blit(ts_surface, (32, 32))

    def _draw_wrapped_text(self, text: str, font: pygame.font.Font, color: Tuple[int, int, int], rect: pygame.Rect) -> None:
        raw_tokens = text.split()
        use_space = len(raw_tokens) > 1
        tokens = raw_tokens if use_space else list(text)
        line = ""
        y = rect.y
        for token in tokens:
            sep = ' ' if (use_space and line) else ''
            test = f"{line}{sep}{token}"
            width, _ = font.size(test)
            if width <= rect.width:
                line = test
            else:
                if line:
                    surface = font.render(line, True, color)
                    self.screen.blit(surface, (rect.x, y))
                    y += font.get_linesize()
                line = token
        if line:
            surface = font.render(line, True, color)
            self.screen.blit(surface, (rect.x, y))


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> None:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG
    cfg = load_config(cfg_path)

    pygame.init()
    pygame.display.set_caption("Zero Assistant Display")

    flags = pygame.FULLSCREEN if cfg["display"].get("fullscreen", False) else 0
    screen = pygame.display.set_mode((cfg["display"]["width"], cfg["display"]["height"]), flags)
    clock = pygame.time.Clock()

    colors = {key: hex_to_rgb(value) for key, value in cfg["colors"].items() if key != "background"}
    colors["background"] = hex_to_rgb(cfg["colors"]["background"])

    renderer = CuteFaceRenderer(screen, cfg)
    feed = JsonStateFeed(BASE_DIR / cfg["messageSource"]["path"])

    running = True
    start_time = time.time()
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False

        snapshot = feed.poll()
        tick = time.time() - start_time
        renderer.draw(snapshot, colors, tick)
        pygame.display.flip()

        clock.tick(cfg["display"].get("fps", 60))

    pygame.quit()


if __name__ == "__main__":
    main()
