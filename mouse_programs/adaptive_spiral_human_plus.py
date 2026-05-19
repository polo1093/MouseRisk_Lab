from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import pyautogui

pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.real_mouse_lab import (
    check_emergency_stop,
    interruptible_sleep,
    parse_region,
)
from tools.mouse_program_protocol import run_click_protocol


Point = Tuple[int, int]
Region = Tuple[int, int, int, int]
VALID_BUTTONS = {"left", "right"}
__all__ = [
    "ClickResult",
    "click_point",
    "click_zone",
    "moveTo",
    "moveToZone",
    "moveTozone",
    "move_to_point",
    "move_to_zone",
]


@dataclass(frozen=True)
class ClickResult:
    """Resultat d'un clic humanise reutilisable par un autre projet."""

    target: Point
    target_region: Region
    movement_region: Region
    click_region: Region
    button: str
    delayed: bool
    clicked: bool
    click_point: Optional[Point]


def parse_point(value: str) -> Point:
    """Convertit une chaine 'x,y' en point souris."""

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("point must use x,y")
    return int(parts[0]), int(parts[1])


def parse_args() -> argparse.Namespace:
    """Lit les options quand le fichier est lance en script CLI."""

    parser = argparse.ArgumentParser(
        description="Human-like spiral mouse program constrained to an inner target box"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--region", required=True, type=parse_region)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--focus-wait", type=float, default=3.0)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=0.06)
    parser.add_argument("--max-duration", type=float, default=0.14)
    parser.add_argument("--spiral-radius", type=float, default=10.0)
    parser.add_argument("--jitter", type=float, default=1.5)
    parser.add_argument("--inner-box-scale", type=float, default=0.70)
    parser.add_argument("--click-box-scale", type=float, default=0.35)
    parser.add_argument("--delay-chance", type=float, default=0.0)
    parser.add_argument("--pre-click-delay-min", type=float, default=0.006)
    parser.add_argument("--pre-click-delay-max", type=float, default=0.018)
    parser.add_argument("--target-point", type=parse_point, default=None)
    parser.add_argument("--button", choices=sorted(VALID_BUTTONS), default="left")
    return parser.parse_args()


def validate_button(button: str) -> str:
    """Verifie que le bouton souris demande est supporte."""

    if button not in VALID_BUTTONS:
        raise ValueError("button must be 'left' or 'right'")
    return button


def validate_motion_options(
    *,
    min_duration: float,
    max_duration: float,
    delay_chance: float,
    delay_min: float,
    delay_max: float,
) -> None:
    """Valide les options communes de mouvement et de delai."""

    if min_duration <= 0 or max_duration < min_duration:
        raise ValueError("duration range is invalid")
    if not 0.0 <= delay_chance <= 1.0:
        raise ValueError("delay_chance must be between 0 and 1")
    if delay_min < 0 or delay_max < delay_min:
        raise ValueError("pre-click delay range is invalid")


def screen_region() -> Region:
    """Retourne toute la zone ecran comme region par defaut."""

    width, height = pyautogui.size()
    return 0, 0, int(width), int(height)


def inner_box(region: Region, scale: float) -> Region:
    """Calcule une box centrale plus petite a partir d'une region."""

    x1, y1, x2, y2 = region
    width = x2 - x1
    height = y2 - y1
    inner_width = max(1, round(width * scale))
    inner_height = max(1, round(height * scale))
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    ix1 = round(cx - inner_width / 2.0)
    iy1 = round(cy - inner_height / 2.0)
    ix2 = ix1 + inner_width
    iy2 = iy1 + inner_height
    return ix1, iy1, ix2, iy2


def random_inner_box(region: Region, scale: float) -> Region:
    """Cree une box aleatoire dans une region, sans depasser ses bords."""

    x1, y1, x2, y2 = region
    width = x2 - x1
    height = y2 - y1
    box_width = max(1, min(width, round(width * scale)))
    box_height = max(1, min(height, round(height * scale)))
    bx1 = random.randint(x1, x2 - box_width)
    by1 = random.randint(y1, y2 - box_height)
    return bx1, by1, bx1 + box_width, by1 + box_height


def clamp_point(point: tuple[float, float], region: Region, margin: int = 8) -> Point:
    """Force un point a rester dans la region, avec une petite marge."""

    x1, y1, x2, y2 = region
    max_margin = max(0, min((x2 - x1) // 2, (y2 - y1) // 2, margin))
    x = min(max(point[0], x1 + max_margin), x2 - max_margin)
    y = min(max(point[1], y1 + max_margin), y2 - max_margin)
    return round(x), round(y)


def point_in_region(point: Point, region: Region, margin: int = 0) -> bool:
    """Dit si un point est dans une region, avec une marge optionnelle."""

    x1, y1, x2, y2 = region
    return x1 + margin <= point[0] <= x2 - margin and y1 + margin <= point[1] <= y2 - margin


def random_target(region: Region) -> Point:
    """Choisit une cible aleatoire dans la region donnee."""

    x1, y1, x2, y2 = region
    width = x2 - x1
    height = y2 - y1
    if random.random() < 0.65:
        cx = random.uniform(x1 + width * 0.18, x2 - width * 0.18)
        cy = random.uniform(y1 + height * 0.18, y2 - height * 0.18)
    else:
        margin = max(1, min(24, width // 4, height // 4))
        cx = random.uniform(x1 + margin, x2 - margin)
        cy = random.uniform(y1 + margin, y2 - margin)
    return clamp_point((cx, cy), region)


def choose_target(region: Region, target_point: Optional[Point]) -> Point:
    """Utilise le point force si donne, sinon choisit une cible aleatoire."""

    if target_point is not None:
        return clamp_point(target_point, region)
    return random_target(region)


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> tuple[float, float]:
    """Calcule un point sur une courbe de Bezier cubique."""

    u = 1.0 - t
    x = (u**3 * p0[0]) + (3 * u**2 * t * p1[0]) + (3 * u * t**2 * p2[0]) + (t**3 * p3[0])
    y = (u**3 * p0[1]) + (3 * u**2 * t * p1[1]) + (3 * u * t**2 * p2[1]) + (t**3 * p3[1])
    return x, y


def ease_in_out(t: float) -> float:
    """Rend le mouvement plus doux: lent au debut et a la fin."""

    return 0.5 - (math.cos(math.pi * t) / 2.0)


def control_points(start: Point, end: Point, region: Region) -> tuple[Point, Point]:
    """Cree deux points de controle pour courber la trajectoire."""

    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    distance = max(1.0, math.hypot(dx, dy))
    nx = -dy / distance
    ny = dx / distance
    bend = random.uniform(-0.22, 0.22) * distance
    p1 = (
        sx + dx * random.uniform(0.25, 0.45) + nx * bend,
        sy + dy * random.uniform(0.15, 0.35) + ny * bend,
    )
    p2 = (
        sx + dx * random.uniform(0.58, 0.82) - nx * bend * 0.55,
        sy + dy * random.uniform(0.62, 0.90) - ny * bend * 0.55,
    )
    return clamp_point(p1, region), clamp_point(p2, region)


def path_to_target(start: Point, end: Point, region: Region, duration: float, spiral_radius: float) -> Iterable[Point]:
    """Genere les points du trajet jusqu'a la cible avec une spirale finale."""

    start = clamp_point(start, region)
    end = clamp_point(end, region)
    p1, p2 = control_points(start, end, region)
    steps = max(12, int(duration * random.uniform(44, 62)))
    previous: Optional[Point] = None
    spiral_turns = random.uniform(2.0, 3.4)
    noise_phase = random.uniform(0.0, math.tau)
    noise_amplitude = random.uniform(0.02, 0.12)

    for index in range(steps):
        progress = index / max(1, steps - 1)
        eased = ease_in_out(progress)
        point = cubic_bezier(start, p1, p2, end, eased)

        if progress > 0.82:
            settle = min(1.0, max(0.0, (progress - 0.82) / 0.18))
            radius = spiral_radius * (1.0 - settle) ** 1.7
            angle = settle * spiral_turns * math.pi
            point = (
                point[0] + math.cos(angle) * radius,
                point[1] + math.sin(angle) * radius * 0.72,
            )

        noise = (1.0 - progress) * math.sin((progress * math.tau) + noise_phase) * noise_amplitude
        candidate = clamp_point((point[0] + noise, point[1] - noise * 0.6), region)
        if candidate != previous:
            previous = candidate
            yield candidate


def move_path(points: Iterable[Point], duration: float) -> None:
    """Deplace reellement la souris sur chaque point du trajet."""

    points = list(points)
    if not points:
        return
    base_sleep = duration / len(points)
    for point in points:
        check_emergency_stop()
        pyautogui.moveTo(point[0], point[1], duration=max(0.001, base_sleep * 0.35))
        interruptible_sleep(max(0.0005, base_sleep * random.uniform(0.02, 0.10)), step=0.002)


def move_path_click_on_enter(
    points: Iterable[Point],
    duration: float,
    click_region: Region,
    *,
    button: str,
    hold_min: float,
    hold_max: float,
    delay_chance: float,
) -> tuple[bool, bool, Optional[Point]]:
    """Clique en down/up des que la souris entre dans la zone active."""

    button = validate_button(button)
    points = list(points)
    if not points:
        return False, False, None

    clicked = False
    delayed = False
    click_point: Optional[Point] = None
    base_sleep = duration / len(points)
    click_margin = max(0, min((click_region[2] - click_region[0]) // 5, (click_region[3] - click_region[1]) // 5, 24))

    for point in points:
        check_emergency_stop()
        pyautogui.moveTo(point[0], point[1], duration=max(0.002, base_sleep * 0.45))
        if not clicked and point_in_region(point, click_region, margin=click_margin):
            delayed = random.random() < delay_chance
            if delayed:
                interruptible_sleep(random.uniform(hold_min, hold_max), step=0.002)
            check_emergency_stop()
            pyautogui.mouseDown(button=button)
            interruptible_sleep(random.uniform(hold_min, hold_max), step=0.002)
            check_emergency_stop()
            pyautogui.mouseUp(button=button)
            clicked = True
            click_point = point
            return clicked, delayed, click_point
        interruptible_sleep(max(0.001, base_sleep * random.uniform(0.04, 0.16)), step=0.002)

    return clicked, delayed, click_point


def move_to_point(
    point: Point,
    *,
    region: Optional[Region] = None,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
) -> Point:
    """Deplace la souris vers un point, sans cliquer."""

    if min_duration <= 0 or max_duration < min_duration:
        raise ValueError("duration range is invalid")
    movement_region = region or screen_region()
    target = clamp_point(point, movement_region)
    start = clamp_point(pyautogui.position(), movement_region)
    duration = random.uniform(min_duration, max_duration)
    move_path(
        path_to_target(start, target, movement_region, duration, spiral_radius),
        duration,
    )
    return target


def moveTo(
    point: Point,
    *,
    region: Optional[Region] = None,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
) -> Point:
    """Deplace la souris vers un point avec le mouvement humanise du fichier."""

    return move_to_point(
        point,
        region=region,
        min_duration=min_duration,
        max_duration=max_duration,
        spiral_radius=spiral_radius,
    )


def move_to_zone(
    region: Region,
    *,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
) -> Point:
    """Choisit un point aleatoire dans une zone et s'y arrete sans cliquer."""

    target = random_target(region)
    return move_to_point(
        target,
        region=region,
        min_duration=min_duration,
        max_duration=max_duration,
        spiral_radius=spiral_radius,
    )


def moveToZone(
    region: Region,
    *,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
) -> Point:
    """Alias camelCase de move_to_zone(...)."""

    return move_to_zone(
        region,
        min_duration=min_duration,
        max_duration=max_duration,
        spiral_radius=spiral_radius,
    )


def moveTozone(
    region: Region,
    *,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
) -> Point:
    """Alias compatible avec le nom moveTozone(...)."""

    return moveToZone(
        region,
        min_duration=min_duration,
        max_duration=max_duration,
        spiral_radius=spiral_radius,
    )


def settle_and_click(
    target: Point,
    region: Region,
    jitter: float,
    delay_chance: float,
    delay_min: float,
    delay_max: float,
    button: str = "left",
) -> bool:
    """Ajoute de petits ajustements autour de la cible, puis clique."""

    button = validate_button(button)
    loops = random.randint(1, 3)
    for _ in range(loops):
        check_emergency_stop()
        jx = random.uniform(-jitter, jitter) * 0.45
        jy = random.uniform(-jitter, jitter) * 0.45
        point = clamp_point((target[0] + jx, target[1] + jy), region)
        pyautogui.moveTo(point[0], point[1], duration=random.uniform(0.035, 0.09))
        interruptible_sleep(random.uniform(0.02, 0.075), step=0.01)

    used_delay = random.random() < delay_chance
    if used_delay:
        interruptible_sleep(random.uniform(delay_min, delay_max), step=0.01)

    check_emergency_stop()
    pyautogui.click(button=button)
    return used_delay


def click_point(
    point: Point,
    *,
    button: str = "left",
    region: Optional[Region] = None,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
    jitter: float = 1.5,
    delay_chance: float = 0.0,
    pre_click_delay_min: float = 0.04,
    pre_click_delay_max: float = 0.18,
) -> bool:
    """Va vers un point precis et clique avec le bouton gauche ou droit.

    Args:
        point: Position ecran finale au format (x, y).
        button: Bouton a cliquer, "left" ou "right".
        region: Zone ou la souris doit rester. Si None, utilise tout l'ecran.
        min_duration: Duree minimale du deplacement vers la cible.
        max_duration: Duree maximale du deplacement vers la cible.
        spiral_radius: Taille de la petite spirale d'approche finale.
        jitter: Amplitude des petits mouvements avant le clic.
        delay_chance: Probabilite entre 0 et 1 d'attendre avant le clic.
        pre_click_delay_min: Delai minimum si le delai est choisi.
        pre_click_delay_max: Delai maximum si le delai est choisi.

    Returns:
        True si un delai pre-clic a ete utilise, sinon False.
    """

    validate_motion_options(
        min_duration=min_duration,
        max_duration=max_duration,
        delay_chance=delay_chance,
        delay_min=pre_click_delay_min,
        delay_max=pre_click_delay_max,
    )
    button = validate_button(button)
    movement_region = region or screen_region()
    target = move_to_point(
        point,
        region=movement_region,
        min_duration=min_duration,
        max_duration=max_duration,
        spiral_radius=spiral_radius,
    )
    return settle_and_click(
        target,
        movement_region,
        jitter,
        delay_chance,
        pre_click_delay_min,
        pre_click_delay_max,
        button,
    )


def click_zone(
    *,
    region: Region,
    target_point: Optional[Point] = None,
    button: str = "left",
    inner_box_scale: float = 0.70,
    click_box_scale: float = 0.35,
    delay_chance: float = 0.0,
    pre_click_delay_min: float = 0.04,
    pre_click_delay_max: float = 0.18,
    min_duration: float = 0.06,
    max_duration: float = 0.14,
    spiral_radius: float = 10.0,
    jitter: float = 1.5,
) -> ClickResult:
    """Clique dans une zone en generant une zone active aleatoire dedans.

    Args:
        region: Zone rouge donnee par l'utilisateur, au format (x1, y1, x2, y2).
        target_point: Point precis a viser. Si None, choisit un point dans la zone verte.
        button: Bouton a cliquer, "left" ou "right".
        inner_box_scale: Taille de la box rouge aleatoire dans la zone de jeu.
        click_box_scale: Taille de la box verte aleatoire, entre 0.2 et 1.0.
        delay_chance: Probabilite entre 0 et 1 d'attendre avant mouseDown.
        pre_click_delay_min: Delai minimum avant/pendant le down-up.
        pre_click_delay_max: Delai maximum avant/pendant le down-up.
        min_duration: Duree minimale du deplacement vers la cible.
        max_duration: Duree maximale du deplacement vers la cible.
        spiral_radius: Taille de la petite spirale d'approche finale.
        jitter: Amplitude des petits mouvements avant le clic.

    Returns:
        ClickResult avec la cible finale, la box verte, clicked et click_point.
    """

    if not 0.1 <= inner_box_scale <= 1.0:
        raise ValueError("inner_box_scale must be between 0.1 and 1.0")
    if not 0.2 <= click_box_scale <= 1.0:
        raise ValueError("click_box_scale must be between 0.2 and 1.0")
    button = validate_button(button)
    movement_region = random_inner_box(region, inner_box_scale)
    click_region = random_inner_box(movement_region, click_box_scale)
    target = choose_target(click_region, target_point)
    start = clamp_point(pyautogui.position(), movement_region)
    duration = random.uniform(min_duration, max_duration)
    clicked, delayed, active_click_point = move_path_click_on_enter(
        path_to_target(start, target, movement_region, duration, spiral_radius),
        duration,
        click_region,
        button=button,
        hold_min=pre_click_delay_min,
        hold_max=pre_click_delay_max,
        delay_chance=delay_chance,
    )
    return ClickResult(
        target=target,
        target_region=click_region,
        movement_region=movement_region,
        click_region=click_region,
        button=button,
        delayed=delayed,
        clicked=clicked,
        click_point=active_click_point,
    )


def adaptive_spiral_human_plus_click(**kwargs: object) -> ClickResult:
    """Alias de compatibilite. Pour nouveau code, utiliser click_zone(...)."""

    return click_zone(**kwargs)


def run(args: argparse.Namespace) -> None:
    """Wrapper CLI/API: execute des clics et affiche la telemetrie du projet."""

    if args.seed is not None:
        random.seed(args.seed)

    pyautogui.PAUSE = 0
    pyautogui.MINIMUM_DURATION = 0
    pyautogui.MINIMUM_SLEEP = 0
    pyautogui.FAILSAFE = True
    print(
        "Program: adaptive_spiral_human_plus | "
        f"clicks={args.count} | region={args.region} | movement_box=random:{args.inner_box_scale:.2f} | "
        f"click_box=random:{args.click_box_scale:.2f} | "
        f"delay_chance={args.delay_chance:.2f} | failsafe=screen-corner"
    )
    print(f"PyAutoGUI: pos={pyautogui.position()} size={pyautogui.size()}")

    def click_once(_index: int) -> ClickResult:
        check_emergency_stop()
        return click_zone(
            region=args.region,
            target_point=args.target_point,
            button=args.button,
            inner_box_scale=args.inner_box_scale,
            click_box_scale=args.click_box_scale,
            delay_chance=args.delay_chance,
            pre_click_delay_min=args.pre_click_delay_min,
            pre_click_delay_max=args.pre_click_delay_max,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            spiral_radius=args.spiral_radius,
            jitter=args.jitter,
        )

    def format_result(index: int, result: ClickResult) -> str:
        return (
            f"{index:02d} target={result.target} button={result.button} "
            f"click_box={result.click_region} clicked={result.clicked} "
            f"click_point={result.click_point} delayed={result.delayed}"
        )

    run_click_protocol(
        count=args.count,
        base_url=args.base_url,
        session_id=args.session_id,
        focus_wait=args.focus_wait,
        click_once=click_once,
        format_result=format_result,
        fetch_telemetry_each_click=False,
    )


def main() -> None:
    """Point d'entree du script quand il est lance par python."""

    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    if not 0.1 <= args.inner_box_scale <= 1.0:
        raise SystemExit("--inner-box-scale must be between 0.1 and 1.0")
    if not 0.2 <= args.click_box_scale <= 1.0:
        raise SystemExit("--click-box-scale must be between 0.2 and 1.0")
    try:
        validate_motion_options(
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            delay_chance=args.delay_chance,
            delay_min=args.pre_click_delay_min,
            delay_max=args.pre_click_delay_max,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    run(args)


if __name__ == "__main__":
    main()
