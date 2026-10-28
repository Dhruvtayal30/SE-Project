"""Real-browser tests (Playwright + Chromium) against the Flask server serving the built frontend.

Run `npm run build` in frontend/ first; these tests are skipped when frontend/dist is missing or
Playwright is not installed. Set SHOTS=1 to also write screenshots to docs/screenshots/.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
pytestmark = pytest.mark.skipif(not (ROOT / "frontend" / "dist" / "index.html").exists(), reason="frontend not built")
MOD_KEY = "Meta" if sys.platform == "darwin" else "Control"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    port = free_port()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    proc = subprocess.Popen([sys.executable, "-m", "cfg_analyzer", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield url
    proc.terminate()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    ctx = browser.new_context(viewport={"width": 1480, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # HTTP 4xx/5xx and aborted requests are deliberate in some tests and are logged by Chromium as "Failed to load resource"
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    pg.goto(base_url)
    pg.wait_for_selector("[data-testid=analyze]")
    yield pg
    assert errors == [], f"browser errors: {errors}"
    ctx.close()


def shot(pg, name):
    if os.environ.get("SHOTS"):
        SHOTS.mkdir(parents=True, exist_ok=True)
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(SHOTS / name))


def load_example(pg, title):
    pg.click("text=Examples")
    pg.click(f"[data-testid=examples-menu] >> text={title}")
    pg.wait_for_function("document.querySelector('[aria-busy]').getAttribute('aria-busy') === 'false'")
    pg.wait_for_timeout(500)


def m_value(pg) -> int:
    return int(pg.inner_text("[data-testid=m-value]"))


def test_first_load_waits_for_analyze_then_shows_the_starter_analysis(page):
    assert page.locator("[data-testid=m-value]").count() == 0
    assert "int process(int n, int mode)" in page.locator(".cm-content").inner_text()
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=m-value]")
    assert m_value(page) == 11
    assert "M = P_d + 1" in page.inner_text("[data-testid=formula]")
    assert page.locator("[data-kind=decision]").count() > 0
    assert page.locator("[data-kind=entry]").count() == 1 and page.locator("[data-kind=exit]").count() == 1
    shot(page, "01-first-analysis.png")


def test_reference_example_matches_report_numbers(page):
    load_example(page, "Switch with compound conditions")
    assert m_value(page) == 9
    assert "M = P_d + 1" in page.inner_text("[data-testid=formula]")
    assert page.locator("[data-testid^=node-]").count() == 19
    page.locator(".convention-toggle input").uncheck()
    page.wait_for_function("document.querySelector('[data-testid=m-value]').textContent === '8'")
    assert "M = 23 − 17 + 2×1 = 8" in page.inner_text("[data-testid=formula]")
    assert page.locator("[data-testid^=node-]").count() == 17
    page.click("[data-testid=tab-paths]")
    assert page.locator("[data-testid^=path-]").count() == 8
    shot(page, "02-switch-and-conditions.png")


def test_node_click_shows_details_and_highlights_source(page):
    load_example(page, "if / else")
    cond = page.locator("[data-kind=decision]")
    cond.click()
    assert "Decision (if condition)" in page.inner_text("[data-testid=node-details]")
    details = page.inner_text("[data-testid=node-details]")
    assert "Incoming (1)" in details and "Outgoing (2)" in details and "True" in details and "False" in details
    # the source line of the condition is highlighted in the editor
    assert page.locator(".cm-active-line").count() == 1
    assert "if (a > b)" in page.locator(".cm-active-line").inner_text()
    assert "is-selected" in cond.get_attribute("class")
    shot(page, "03-node-selected.png")


def test_clicking_a_source_line_selects_its_node(page):
    load_example(page, "while loop")
    page.locator(".cm-line", has_text="while (n > 0)").click()
    page.wait_for_selector("[data-testid=node-details]")
    assert "while-loop condition" in page.inner_text("[data-testid=node-details]")
    assert page.locator(".cfg-node.is-selected[data-kind=decision]").count() == 1


def test_path_highlight(page):
    load_example(page, "for loop with continue")
    page.click("[data-testid=tab-paths]")
    page.click("[data-testid=path-2]")
    on_path = page.locator(".cfg-node.is-path").count()
    assert 2 <= on_path < page.locator("[data-testid^=node-]").count()
    assert page.locator(".cfg-node.is-dim").count() > 0
    shot(page, "04-path-highlight.png")
    page.click("text=Clear highlight")
    assert page.locator(".cfg-node.is-path").count() == 0


def test_shortest_path_from_entry(page):
    load_example(page, "while loop")
    page.locator("[data-kind=block]").last.click()
    page.click("text=Highlight")
    assert page.locator(".cfg-node.is-path").count() >= 3


def test_loop_back_edge_is_flagged(page):
    load_example(page, "while loop")
    assert page.locator("path.is-back").count() == 1
    assert "Loops (back edges)" in page.inner_text("[data-testid=metrics-panel]")


def test_syntax_error_shows_message_and_no_graph(page):
    page.locator(".cm-content").click()
    page.keyboard.press(f"{MOD_KEY}+A")
    page.keyboard.type("int f(void) {\n int x = 1\n return x;\n}")
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=error-state]")
    txt = page.inner_text("[data-testid=error-state]")
    assert "Syntax error" in txt and "line 2" in txt and "missing ';'" in txt
    assert page.locator("[data-testid=graph]").count() == 0           # never a graph for invalid code
    assert page.locator(".cm-error-line").count() == 1
    shot(page, "05-syntax-error.png")
    page.click("text=Back to editor")                                  # interface stays usable
    page.locator(".cm-content").click()
    page.keyboard.press(f"{MOD_KEY}+A")
    page.keyboard.type("int f(void) { return 1; }")
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=m-value]")
    assert m_value(page) == 1


def test_unsupported_construct_is_reported(page):
    page.locator(".cm-content").click()
    page.keyboard.press(f"{MOD_KEY}+A")
    page.keyboard.type("int f(int x) {\n#ifdef A\n x++;\n#endif\n return x; }")
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=error-state]")
    assert "Unsupported construct" in page.inner_text("[data-testid=error-state]")


def test_editing_marks_the_graph_stale(page):
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=m-value]")
    page.locator(".cm-content").click()
    page.keyboard.press(f"{MOD_KEY}+End")
    page.keyboard.type("// edit")
    assert page.locator(".banner.stale").count() == 1
    page.click("[data-testid=analyze]")
    page.wait_for_function("document.querySelectorAll('.banner.stale').length === 0")


def test_multi_function_selector(page):
    load_example(page, "Several functions in one file")
    sel = page.locator("[data-testid=function-select]")
    assert sel.input_value() == "main"
    sel.select_option("clamp")
    page.wait_for_function("document.querySelector('.fn-name').textContent.includes('clamp')")
    assert m_value(page) == 3


def test_unreachable_and_infinite_loop_are_explained(page):
    load_example(page, "Unreachable code")
    assert page.locator(".cfg-node.is-dead").count() == 1
    assert page.locator(".cm-dead-line").count() >= 1
    page.click("[data-testid=tab-warnings]")
    assert "Unreachable code" in page.inner_text("[data-testid=warnings-panel]")
    load_example(page, "Infinite loop")
    assert "EXIT is not reachable" in page.inner_text("[data-testid=metrics-panel]")
    page.click("[data-testid=tab-paths]")
    assert page.locator("[data-testid=paths-unavailable]").count() == 1
    shot(page, "06-infinite-loop.png")


def test_exports_download_valid_files(page, tmp_path):
    load_example(page, "if / else")
    for kind, ext in (("svg", ".svg"), ("png", ".png"), ("json", ".json"), ("md", ".md")):
        page.click("text=Export")
        with page.expect_download() as dl:
            page.click(f"[data-testid=export-{kind}]")
        path = tmp_path / ("f" + ext)
        dl.value.save_as(path)
        data = path.read_bytes()
        assert len(data) > 100
        if kind == "svg":
            assert data.startswith(b"<svg") and data.count(b"<path") >= 7 and b"max_of" in data
        elif kind == "png":
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
        elif kind == "json":
            assert json.loads(data)["complexity"]["value"] == 2
        else:
            assert b"Cyclomatic complexity" in data


def test_upload_c_file(page, tmp_path):
    f = tmp_path / "t.c"
    f.write_text("int g(int a){ if (a) return 1; if (a>2) return 2; return 0; }\n")
    page.set_input_files("[data-testid=file-input]", str(f))
    page.wait_for_function("document.querySelector('.fn-name') && document.querySelector('.fn-name').textContent.includes('g()')")
    assert m_value(page) == 3


def test_oversized_upload_is_refused_with_message(page, tmp_path):
    f = tmp_path / "big.c"
    f.write_text("int f(){}\n" + " " * 120_000)
    page.set_input_files("[data-testid=file-input]", str(f))
    page.wait_for_selector(".banner.danger")
    assert "limit" in page.inner_text(".banner.danger")


def test_layout_toggle_and_reset_do_not_change_metrics(page):
    load_example(page, "Nested loops with break and continue")
    before = page.inner_text("[data-testid=metrics-panel]")
    page.click("text=Top-down")
    page.wait_for_timeout(500)
    page.click("text=Reset layout")
    page.wait_for_timeout(500)
    assert page.inner_text("[data-testid=metrics-panel]") == before and page.locator("[data-testid^=node-]").count() == 11


def test_dragging_a_node_does_not_change_metrics(page):
    load_example(page, "if / else")
    before = page.inner_text("[data-testid=metrics-panel]")
    box = page.locator("[data-kind=block]").first.bounding_box()
    page.mouse.move(box["x"] + 20, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 120, box["y"] + 60, steps=6)
    page.mouse.up()
    assert page.inner_text("[data-testid=metrics-panel]") == before


def test_mobile_layout_has_no_horizontal_scroll(browser, base_url):
    ctx = browser.new_context(viewport={"width": 390, "height": 800})
    pg = ctx.new_page()
    pg.goto(base_url)
    pg.click("[data-testid=analyze]")
    pg.wait_for_selector("[data-testid=graph]")
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert pg.locator(".mobile-tabs").is_visible()
    shot(pg, "07-mobile-graph.png")
    pg.click(".mobile-tabs >> text=Details")
    pg.wait_for_selector("[data-testid=metrics-panel]")
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    pg.click(".mobile-tabs >> text=Code")
    assert pg.locator("[data-testid=code-editor]").is_visible()
    ctx.close()


def test_methodology_dialog(page):
    page.click("text=Methodology")
    assert "E − N + 2P" in page.inner_text("[role=dialog]")
    page.click("[role=dialog] >> text=Close")
    assert page.locator("[role=dialog]").count() == 0


def test_backend_down_shows_actionable_error(page):
    page.route("**/api/analyze", lambda r: r.abort())
    page.click("[data-testid=analyze]")
    page.wait_for_selector("[data-testid=error-state]")
    assert "backend" in page.inner_text("[data-testid=error-state]").lower()
