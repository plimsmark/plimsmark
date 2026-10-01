"""Real-browser, offline checks for the generated report (separate from pytest).

Run after build_site.py:
  uv run --no-project --with playwright --python .venv/bin/python \
    python scripts/check_site_browser.py

Uses the locally installed Chrome. No browser download, server, or live RPC calls.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parent.parent
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def check_replay(page):
    page.locator(".sonar-scope").scroll_into_view_if_needed()
    page.wait_for_selector(".pg-controls", state="visible", timeout=2000)
    page.wait_for_function("document.querySelector('.sonar').dataset.playing === 'true'")
    page.locator(".pg-play").click()
    assert page.locator(".sonar").get_attribute("data-playing") == "false"
    paused = page.locator(".pg-page").inner_text()
    page.wait_for_timeout(550)
    assert page.locator(".pg-page").inner_text() == paused, "pause did not stop the replay"

    page.locator(".pg-restart").click()
    page.evaluate("window.scrollTo({top:0, behavior:'instant'})")
    page.wait_for_function("document.querySelector('.sonar').dataset.playing === 'false'")
    offscreen = page.locator(".pg-page").inner_text()
    page.wait_for_timeout(550)
    assert page.locator(".pg-page").inner_text() == offscreen, "off-screen replay kept running"
    page.locator(".sonar-scope").scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('.sonar').dataset.playing === 'true'")
    page.locator(".pg-play").click()

    # Seek to every real observation, independently of the animation's state.
    points = page.locator(".pg-dot").evaluate_all(
        "els => els.map(e => ({...e.dataset, x:e.getAttribute('cx'), y:e.getAttribute('cy')}))"
    )
    origin = page.locator(".sonar").evaluate("e => [e.dataset.startX, e.dataset.startY]")
    expected_path = f"M{origin[0]},{origin[1]}"
    for point in points:
        page.locator(".pg-slider").fill(point["page"])
        expected_path += f" V{point['y']} H{point['x']}"
        assert page.locator(".pg-page").inner_text() == point["page"]
        assert page.locator(".pg-nodes").inner_text() == point["nodes"]
        assert page.locator(".pg-total").inner_text().replace(",", "") == point["cum"]
        assert page.locator(".pg-next").inner_text() == point["hasNext"]
        assert page.locator(".seabed").get_attribute("d") == expected_path
        assert page.locator(".pg-head").get_attribute("cx") == point["x"]
        assert page.locator(".pg-head").get_attribute("cy") == point["y"]

    # Restart from the middle must synchronously return to the first real page.
    page.locator(".pg-slider").fill(str(len(points) // 2))
    reset = page.locator(".pg-restart").evaluate("""button => {
      button.click();
      return {page:document.querySelector('.pg-page').textContent,
        total:document.querySelector('.pg-total').textContent,
        playing:document.querySelector('.sonar').dataset.playing};
    }""")
    assert reset == {"page": "1", "total": points[0]["cum"], "playing": "true"}
    # A genuine timer advances the data, not just a decorative sweep.
    page.wait_for_function("Number(document.querySelector('.pg-page').textContent) >= 2")
    page.locator(".pg-play").click()
    assert 1 < int(page.locator(".pg-page").inner_text()) < len(points)

    # Headless Chrome keeps background tabs visible. Simulate the Page Visibility
    # state explicitly, dispatch the real event, and restore the native getters.
    def visibility(hidden):
        page.evaluate("""hidden => {
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>hidden});
          Object.defineProperty(document,'visibilityState',{
            configurable:true,get:()=>hidden?'hidden':'visible'
          });
          document.dispatchEvent(new Event('visibilitychange'));
        }""", hidden)

    try:
        page.locator(".pg-play").click()
        visibility(True)
        assert page.locator(".sonar").get_attribute("data-playing") == "false"
        hidden_page = page.locator(".pg-page").inner_text()
        page.wait_for_timeout(550)
        assert page.locator(".pg-page").inner_text() == hidden_page
        visibility(False)
        assert page.locator(".sonar").get_attribute("data-playing") == "true"
        page.wait_for_function(
            "n => Number(document.querySelector('.pg-page').textContent) > n",
            arg=int(hidden_page),
        )
        page.locator(".pg-play").click()
        manual_page = page.locator(".pg-page").inner_text()
        visibility(True)
        visibility(False)
        page.wait_for_timeout(550)
        assert page.locator(".sonar").get_attribute("data-playing") == "false"
        assert page.locator(".pg-page").inner_text() == manual_page, "manual pause auto-resumed"
    finally:
        page.evaluate("""() => {
          delete document.hidden;
          delete document.visibilityState;
          document.dispatchEvent(new Event('visibilitychange'));
        }""")

    # Finish the actual playback, without waiting through every earlier page.
    page.locator(".pg-slider").fill(str(len(points) - 1))
    page.locator(".pg-play").click()
    page.wait_for_function("document.querySelector('.sonar').dataset.playing === 'false'")
    assert page.locator(".pg-page").inner_text() == str(len(points))
    assert page.locator(".pg-next").inner_text() == "false"
    assert page.locator(".seabed").get_attribute("d") == expected_path

    page.locator(".pg-slider").focus()
    page.keyboard.press("Home")
    assert page.locator(".pg-page").inner_text() == "1"
    page.keyboard.press("ArrowRight")
    assert page.locator(".pg-page").inner_text() == "2"
    page.keyboard.press("End")
    assert page.locator(".pg-page").inner_text() == str(len(points))
    return {"pages_checked": len(points), "final_events": points[-1]["cum"],
            "restart_from_middle": "passed", "visibility_change_simulation": "passed",
            "manual_pause_preserved": "passed"}


def check_transitions(page):
    # Start at the top of a genuinely fresh document, before any section visits.
    page.goto("about:blank")
    page.goto((ROOT / "docs" / "index.html").as_uri() + "?qa=fresh-scroll")
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.wait_for_timeout(60)
    assert page.locator(".depth > .inner:not(.shown)").count() > 0
    page.evaluate("window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})")
    page.wait_for_timeout(1000)
    assert page.locator(".depth > .inner").evaluate_all(
        "els => els.every(e => getComputedStyle(e).opacity === '1')"
    ), "first-visit fast scroll stranded a hidden section"
    assert page.locator(".gauge a[aria-current]").get_attribute("href") == "#sec-6"
    page.evaluate("""() => {
      window.__sectionEntries=[];
      document.addEventListener('animationstart', e => {
        if(e.animationName === 'depth-enter') window.__sectionEntries.push({
          section:e.target.closest('.depth').id,
          direction:e.target.closest('.depth').dataset.direction
        });
      });
      window.scrollTo({top:0, behavior:'instant'});
    }""")
    page.wait_for_timeout(60)
    visited = []
    for number in [*range(1, 7), *range(5, 0, -1)]:
        sid = f"sec-{number}"
        before = page.evaluate("window.__sectionEntries.length")
        page.locator(f'.gauge a[href="#{sid}"]').click()
        page.wait_for_function(
            "sid => document.querySelector('.gauge a[aria-current]')?.hash === '#'+sid", arg=sid
        )
        page.wait_for_function(
            "p => window.__sectionEntries.slice(p.before).some(e => e.section === p.sid)",
            arg={"before": before, "sid": sid}, timeout=2500,
        )
        page.wait_for_timeout(900)
        content = page.locator(f"#{sid} > .inner")
        assert content.evaluate("e => getComputedStyle(e).opacity") == "1", sid
        assert page.locator(f"#{sid}").get_attribute("data-direction") == (
            "up" if len(visited) >= 6 else "down"
        )
        visited.append(sid)
    # Momentum-style jumps must not strand any section at opacity zero.
    page.evaluate("window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})")
    page.wait_for_timeout(1000)
    assert page.locator(".depth > .inner").evaluate_all(
        "els => els.every(e => getComputedStyle(e).opacity === '1')"
    )
    assert page.locator(".gauge a[aria-current]").get_attribute("href") == "#sec-6"
    return {"sections_down": visited[:6], "sections_up": visited[6:],
            "first_visit_fast_scroll": "passed", "fast_scroll": "passed"}


def assert_static_report(page):
    assert page.locator(".depth > .inner").evaluate_all(
        "els => els.every(e => getComputedStyle(e).opacity === '1')"
    )
    assert page.locator(".pg-controls").is_hidden()
    assert page.locator(".pg-page").inner_text() == page.locator(".sonar").get_attribute("data-pages")
    assert page.locator(".pg-next").inner_text() == "false"
    assert page.locator(".pg-dot").evaluate_all(
        "els => els.every(e => getComputedStyle(e).visibility === 'visible')"
    )
    assert page.locator("[data-count]").evaluate_all(
        "els => els.every(e => e.textContent === e.dataset.count)"
    )
    assert page.evaluate("document.getAnimations().length") == 0, "motion remains enabled"


def check_motion_preferences(page):
    page.locator(".sonar-scope").scroll_into_view_if_needed()
    page.locator(".pg-restart").click()
    page.wait_for_function("Number(document.querySelector('.pg-page').textContent) >= 2")
    page.emulate_media(reduced_motion="reduce")
    page.wait_for_function("!document.documentElement.classList.contains('js-anim')")
    page.wait_for_timeout(100)
    assert_static_report(page)
    # Navigation is functional, but no transitions or replay run under reduced motion.
    page.locator('.gauge a[href="#sec-5"]').click()
    page.wait_for_function("document.querySelector('.gauge a[aria-current]')?.hash === '#sec-5'")
    assert page.evaluate("document.getAnimations().length") == 0
    page.emulate_media(reduced_motion="no-preference")
    page.wait_for_function("document.documentElement.classList.contains('js-anim')")
    page.locator(".sonar-scope").scroll_into_view_if_needed()
    assert page.locator(".pg-controls").is_visible()
    page.locator(".pg-restart").click()
    page.wait_for_function("Number(document.querySelector('.pg-page').textContent) >= 2")
    page.locator(".pg-play").click()
    return "passed (including preference changes during playback)"


def check_mobile(page):
    page.set_viewport_size({"width": 375, "height": 812})
    page.reload()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal overflow"
    replay = check_replay(page)
    transitions = check_transitions(page)
    targets = page.locator(".gauge a,.pg-controls button,.pg-slider").evaluate_all(
        "els => els.map(e => ({label:e.getAttribute('aria-label')||e.textContent, "
        "width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))"
    )
    assert all(target["width"] >= 44 and target["height"] >= 44 for target in targets), targets
    assert page.locator(".gauge a").evaluate_all(
        "els => els.every(e => {const r=e.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth;})"
    ), "mobile navigation runs outside the viewport"
    return {"width": 375, "replay": replay, "transitions": transitions, "touch_targets": "passed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=("replay", "transitions", "all"), default="all")
    parser.add_argument("--output", type=Path, help="Optional JSON result file")
    parser.add_argument("--screenshots", type=Path, help="Optional directory for visual QA")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROME), headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        context.on("page", lambda p: p.on("pageerror", lambda error: errors.append(str(error))))
        context.on("request", lambda request: requests.append(request.url))
        context.route("https://**/*", lambda route: route.abort())
        context.route("http://**/*", lambda route: route.abort())
        page = context.new_page()
        page.goto((ROOT / "docs" / "index.html").as_uri())
        result: dict = {}
        if args.only in ("replay", "all"):
            result["replay"] = check_replay(page)
        if args.only in ("transitions", "all"):
            result["transitions"] = check_transitions(page)
        if args.only == "all":
            result["motion_preferences"] = check_motion_preferences(page)
            result["mobile"] = check_mobile(page)
            if args.screenshots:
                args.screenshots.mkdir(parents=True, exist_ok=True)
                page.locator(".sonar").evaluate("e => window.scrollTo({top:scrollY+e.getBoundingClientRect().top-16,behavior:'instant'})")
                page.wait_for_timeout(1000)
                page.screenshot(path=str(args.screenshots / "replay-mobile.png"))
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.locator(".pg-slider").fill("14")
                page.wait_for_timeout(1000)
                page.locator(".sonar").screenshot(path=str(args.screenshots / "replay-desktop.png"))
                page.locator(".terminal").screenshot(path=str(args.screenshots / "archived-response.png"))
            for mode, options in (
                ("reduced_motion", {"reduced_motion": "reduce"}),
                ("no_javascript", {"java_script_enabled": False}),
            ):
                fallback = browser.new_context(viewport={"width": 375, "height": 812}, **options)
                fallback.on("page", lambda p: p.on("pageerror", lambda error: errors.append(str(error))))
                fallback.on("request", lambda request: requests.append(request.url))
                fallback.route("https://**/*", lambda route: route.abort())
                fallback.route("http://**/*", lambda route: route.abort())
                static_page = fallback.new_page()
                static_page.goto((ROOT / "docs" / "index.html").as_uri())
                assert_static_report(static_page)
                assert static_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                result[mode] = "passed"
                fallback.close()
        assert not errors, errors
        assert all(url.startswith("file:") for url in requests), requests
        result.update({"console_errors": errors, "external_requests": []})
        context.close()
        browser.close()
    output = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
