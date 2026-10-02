"""Real-browser, offline checks for the generated report (separate from pytest).

Run after build_site.py:
  uv run --no-project --with playwright --python .venv/bin/python \
    python scripts/check_site_browser.py

Uses locally installed Chrome by default; --browser webkit uses Playwright's
installed WebKit build. This script never downloads a browser or calls live RPCs.
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
    page.goto("about:blank")
    page.goto((ROOT / "docs" / "index.html").as_uri() + "?qa=fresh-scroll")
    page.wait_for_selector(".scene-intro", timeout=2000)
    page.evaluate("window.scrollTo({top:document.documentElement.scrollHeight,behavior:'instant'})")
    page.wait_for_timeout(200)
    assert page.locator(".depth > .inner,.motion-item").evaluate_all(
        "els => els.every(e => getComputedStyle(e).opacity === '1')"
    ), "first-visit fast scroll stranded hidden report content"
    assert page.locator(".gauge a[aria-current]").get_attribute("href") == "#sec-6"
    page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
    page.wait_for_timeout(100)

    def sample_scene(sid, progress):
        scene = page.locator(f"#{sid} .scene-intro")
        scene.evaluate("""(e,p) => window.scrollTo({
          top:scrollY+e.getBoundingClientRect().top+(e.clientHeight-e.querySelector('.scene-stage').offsetHeight)*p,
          behavior:'instant'
        })""", progress)
        page.wait_for_function("""({sid,progress}) => {
          const e=document.querySelector('#'+sid+' .scene-intro');
          return Math.abs(Number(getComputedStyle(e).getPropertyValue('--scene-progress'))-progress)<.01;
        }""", arg={"sid":sid,"progress":progress}, timeout=3000)
        return scene.evaluate("""e => ({
          progress:Number(getComputedStyle(e).getPropertyValue('--scene-progress')),
          spin:getComputedStyle(e.querySelector('.art-motion')).getPropertyValue('--scene-spin'),
          transform:getComputedStyle(e.querySelector('.art-motion')).transform,
          plane:e.querySelector('.data-plane')?getComputedStyle(e.querySelector('.data-plane')).transform:null,
          stageTop:e.querySelector('.scene-stage').getBoundingClientRect().top
        })""")

    scenes = []
    for sid in ["hero", *(f"sec-{n}" for n in range(1, 7))]:
        start = sample_scene(sid, .12)
        middle = sample_scene(sid, .52)
        end = sample_scene(sid, .88)
        back = sample_scene(sid, .12)
        for requested, sample in ((.12,start),(.52,middle),(.88,end),(.12,back)):
            assert abs(sample["progress"]-requested) < .01, (sid,requested,sample)
            assert abs(sample["stageTop"]) < 2, (sid,"scene stage is not pinned",sample)
        assert len({s["spin"] for s in (start,middle,end)}) == 3, (sid,"spin is not scroll-driven")
        assert len({s["transform"] for s in (start,middle,end)}) == 3, sid
        # Separation opens then closes; symmetric endpoints may intentionally match.
        if start['plane'] is not None:
            assert middle["plane"] != start["plane"], (sid,"layers do not separate")
        assert start["transform"] == back["transform"], (sid,"scroll reversal does not restore scene")
        page.wait_for_timeout(350)
        assert page.locator(f"#{sid} .art-motion").evaluate("e=>getComputedStyle(e).transform") == back["transform"], (
            sid,"scene keeps playing while scroll is stopped"
        )
        scenes.append(sid)

    # Real wheel input must change the scene too, not just scripted jump hooks.
    sample_scene("sec-2", .1)
    before = page.locator("#sec-2 .art-motion").evaluate("e=>getComputedStyle(e).transform")
    page.mouse.move(250,350)
    page.mouse.wheel(0,120)
    page.wait_for_timeout(150)
    after = page.locator("#sec-2 .art-motion").evaluate("e=>getComputedStyle(e).transform")
    assert before != after, "wheel scroll did not animate the layers"

    visited=[]
    for n in [*range(1,7),*range(5,0,-1)]:
        sid=f"sec-{n}"
        page.locator(f'.gauge a[href="#{sid}"]').click()
        page.wait_for_function(
            "sid => document.querySelector('.gauge a[aria-current]')?.hash === '#'+sid", arg=sid
        )
        page.wait_for_timeout(900)
        assert page.locator(f"#{sid} > .inner").evaluate("e=>getComputedStyle(e).opacity") == "1"
        visited.append(sid)

    block=page.locator("#sec-2 > .inner > h3").first
    block.evaluate("e=>{let top=0;for(let p=e;p;p=p.offsetParent)top+=p.offsetTop;window.scrollTo({top:top-innerHeight*.9,behavior:'instant'});}")
    page.wait_for_timeout(100)
    entry=block.evaluate("e=>({opacity:getComputedStyle(e).opacity,transform:getComputedStyle(e).transform})")
    page.mouse.wheel(0,230)
    page.wait_for_timeout(150)
    settled=block.evaluate("e=>({opacity:getComputedStyle(e).opacity,transform:getComputedStyle(e).transform})")
    assert float(settled["opacity"])>float(entry["opacity"]), "content does not reveal with the scroll"
    assert settled["transform"] != entry["transform"]
    return {"scenes_scrubbed_and_reversed":scenes,"sections_down":visited[:6],"sections_up":visited[6:],
            "first_visit_fast_scroll":"passed","real_wheel_motion":"passed","per_block_reveal":"passed"}


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
    page.locator('.pg-controls').scroll_into_view_if_needed()
    page.wait_for_timeout(100)
    targets = page.locator(".gauge a,.pg-controls button,.pg-slider").evaluate_all(
        "els => els.map(e => ({label:e.getAttribute('aria-label')||e.textContent, "
        "width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))"
    )
    assert all(target["width"] >= 44 and target["height"] >= 44 for target in targets), targets
    assert page.locator(".gauge a").evaluate_all(
        "els => els.every(e => {const r=e.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth;})"
    ), "mobile navigation runs outside the viewport"
    return {"width": 375, "replay": replay, "transitions": transitions, "touch_targets": "passed"}


def check_responsive_scenes(page):
    checked=[]
    for width,height in ((375,667),(768,1024),(1280,720)):
        page.set_viewport_size({"width":width,"height":height})
        page.goto("about:blank")
        page.goto((ROOT / "docs" / "index.html").as_uri())
        for sid in ("hero", *(f"sec-{n}" for n in range(1,7))):
            page.locator('#'+sid).evaluate(
                "e=>window.scrollTo({top:scrollY+e.getBoundingClientRect().top,behavior:'instant'})"
            )
            page.wait_for_timeout(100)
            geometry=page.locator('#'+sid+' .scene-stage').evaluate("""e=>{
              const copy=e.querySelector('.scene-copy');
              return {docWidth:document.documentElement.scrollWidth, viewport:innerWidth,
                copyBottom:copy.getBoundingClientRect().bottom,
                footerTop:e.querySelector('.scene-bottom').getBoundingClientRect().top,
                copyScroll:copy.scrollWidth,copyWidth:copy.clientWidth};
            }""")
            assert geometry['docWidth']<=width,(sid,geometry)
            assert geometry['copyScroll']<=geometry['copyWidth']+1,(sid,geometry)
            assert geometry['copyBottom']<geometry['footerTop']-8,(sid,geometry)
            checked.append({"width":width,"height":height,"section":sid})
    return {"views_checked":len(checked),"widths":[375,768,1280],"issues":[]}


def check_review_regressions(page):
    """Exercise the breakpoints and fallback states found by independent review."""
    failures, checks = [], []
    for width in (821, 900, 1024, 1100, 1280, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto((ROOT / "docs" / "index.html").as_uri())
        page.locator('#sec-1 .lede').evaluate("""e => {
          const nav=document.querySelector('.gauge a');
          const n=nav.getBoundingClientRect();
          let top=0;for(let p=e;p;p=p.offsetParent)top+=p.offsetTop;
          scrollTo({top:top-n.top,behavior:'instant'});
        }""")
        page.wait_for_timeout(150)
        geometry=page.evaluate("""() => {
          const text=document.querySelector('#sec-1 .lede strong').getBoundingClientRect();
          const links=[...document.querySelectorAll('.gauge a')].map(e=>e.getBoundingClientRect());
          return {textLeft:text.left,navRight:Math.max(...links.map(r=>r.right)),
            overlap:links.some(r=>r.left<text.right && r.right>text.left && r.top<text.bottom && r.bottom>text.top)};
        }""")
        checks.append({"navigation_width":width, **geometry})
        if geometry['overlap']:
            failures.append({"issue":"navigation overlays report text","width":width,**geometry})
        for sid in ('sec-1','sec-2','sec-4','sec-6'):
            page.locator('#'+sid).evaluate("e=>scrollTo({top:scrollY+e.getBoundingClientRect().top+150,behavior:'instant'})")
            page.wait_for_timeout(100)
            intro=page.locator('#'+sid+' .scene-copy').evaluate("""e=>{
              const copy=e.getBoundingClientRect();
              const links=[...document.querySelectorAll('.gauge a')].map(a=>a.getBoundingClientRect());
              return {copyLeft:copy.left,navRight:Math.max(...links.map(r=>r.right)),
                overlap:links.some(r=>r.left<copy.right && r.right>copy.left && r.top<copy.bottom && r.bottom>copy.top)};
            }""")
            if intro['overlap']:
                failures.append({"issue":"navigation overlays scene copy","width":width,"section":sid,**intro})
            annotation=page.locator('#'+sid+' .art-coordinate')
            if annotation.is_visible():
                bounds=annotation.bounding_box()
                assert bounds
                if bounds['x']<0 or bounds['x']+bounds['width']>width:
                    failures.append({"issue":"decorative caption clipped","width":width,"section":sid})

    for width,height in ((375,667),(812,375),(1280,720)):
        page.set_viewport_size({"width":width,"height":height})
        page.goto("about:blank")
        page.goto((ROOT / "docs" / "index.html").as_uri())
        page.wait_for_timeout(100)
        for sid in ('hero','sec-2','sec-4','sec-6'):
            stage=page.locator('#'+sid+' .scene-stage')
            initial=stage.evaluate("""e=>({height:e.offsetHeight,position:getComputedStyle(e).position,
              introHeight:e.parentElement.offsetHeight})""")
            if initial['height']>height+1 and initial['position']=='sticky':
                failures.append({"issue":"oversized scene is still sticky","viewport":[width,height],"section":sid,**initial})
                continue
            if initial['position']!='sticky':
                if initial['introHeight']>initial['height']+2:
                    failures.append({"issue":"non-sticky fallback retains pin spacer","section":sid,**initial})
                checks.append({"viewport":[width,height],"section":sid,"unpinned":True})
                continue
            for progress in (.12,.52,.88):
                page.locator('#'+sid+' .scene-intro').evaluate("""(e,p)=>{
                  const stage=e.querySelector('.scene-stage');
                  scrollTo({top:scrollY+e.getBoundingClientRect().top+(e.clientHeight-stage.offsetHeight)*p,behavior:'instant'});
                }""",progress)
                page.wait_for_timeout(100)
                actual=stage.evaluate("""e=>({top:e.getBoundingClientRect().top,
                  progress:Number(getComputedStyle(e.parentElement).getPropertyValue('--scene-progress')),
                  eyebrowTop:e.querySelector('.scene-eyebrow').getBoundingClientRect().top,
                  headerBottom:document.querySelector('.site-header').getBoundingClientRect().bottom})""")
                if abs(actual['top'])>2 or abs(actual['progress']-progress)>.015:
                    failures.append({"issue":"sticky range mismatch","viewport":[width,height],"section":sid,"wanted":progress,**actual})
                if actual['eyebrowTop']<actual['headerBottom']+4:
                    failures.append({"issue":"parallax text hidden under header","viewport":[width,height],"section":sid,**actual})
            checks.append({"viewport":[width,height],"section":sid,"pinned_samples":3})

    page.set_viewport_size({"width":1440,"height":1000})
    page.goto((ROOT / "docs" / "index.html").as_uri())
    page.wait_for_timeout(100)
    if page.locator('#hero .buoy').count():
        failures.append({"issue":"duplicate floating mark remains over the main logo"})

    # Without JS the rail must own a contrasting background on either palette.
    browser=page.context.browser
    assert browser
    fallback=browser.new_context(java_script_enabled=False,viewport={"width":1440,"height":1000})
    fallback.route('http://**/*',lambda route:route.abort())
    fallback.route('https://**/*',lambda route:route.abort())
    static=fallback.new_page()
    static.goto((ROOT / 'docs' / 'index.html').as_uri())

    def rgba(value):
        import re
        parts=[float(n) for n in re.findall(r'[\d.]+',value)]
        return parts[:3]+[parts[3] if len(parts)>3 else 1]

    def composite(front,back):
        return [front[i]*front[3]+back[i]*(1-front[3]) for i in range(3)]+[1]

    def luminance(color):
        linear=[v/255/12.92 if v/255<=.04045 else ((v/255+.055)/1.055)**2.4 for v in color[:3]]
        return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))

    for sid in ('sec-4','sec-5'):
        static.locator('#'+sid).evaluate("e=>scrollTo({top:scrollY+e.getBoundingClientRect().top,behavior:'instant'})")
        link=static.locator(f'.gauge a[href="#{sid}"]')
        for interaction in ('hover','focus'):
            getattr(link,interaction)()
            static.wait_for_timeout(300)
            colors=link.evaluate("""e=>({foreground:getComputedStyle(e).color,
              nav:getComputedStyle(e.closest('.gauge')).backgroundColor,
              section:getComputedStyle(document.querySelector(e.getAttribute('href'))).backgroundColor})""")
            background=composite(rgba(colors['nav']),rgba(colors['section']))
            foreground=composite(rgba(colors['foreground']),background)
            values=sorted((luminance(foreground),luminance(background)))
            ratio=(values[1]+.05)/(values[0]+.05)
            checks.append({"no_js":sid,"state":interaction,"contrast":round(ratio,2)})
            if ratio<4.5:
                failures.append({"issue":"no-JS navigation contrast","section":sid,"state":interaction,"ratio":ratio,**colors})
    fallback.close()
    assert not failures,json.dumps(failures,indent=2)
    return {"checks":checks,"issues":[]}


def check_fleet_layout(page):
    """Positioning and bobbing must compose, including at mid-animation."""
    samples=[]
    for width in (375,768,1440):
        page.set_viewport_size({"width":width,"height":1000})
        page.goto((ROOT/'docs'/'index.html').as_uri())
        page.locator('.ships').scroll_into_view_if_needed()
        page.wait_for_timeout(120)
        frames=[]
        for time_ms in (0,1150,2300,3450):
            geometry=page.locator('.ships').evaluate("""(svg,time)=>{
              svg.getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=time;});
              return [...svg.querySelectorAll('.ship')].map(e=>{
                const r=e.querySelector('.shiplabel').getBoundingClientRect();
                const s=e.getScreenCTM();
                const bbox=e.getBBox();
                return {label:e.querySelector('.shiplabel').textContent,left:r.left,right:r.right,labelTop:r.top,
                  centerX:s.e,y:s.f,width:bbox.width,outerAnimation:e.getAnimations().length,
                  motion:getComputedStyle(e.querySelector('.ship-motion')).transform};
              });
            }""",time_ms)
            assert len(geometry)==4
            assert len({round(g['centerX'],2) for g in geometry})==4,(width,time_ms,geometry)
            assert all(a['right']+3<b['left'] for a,b in zip(geometry,geometry[1:])),(width,time_ms,geometry)
            assert all(g['outerAnimation']==0 for g in geometry),'animation overwrites positioning group'
            frames.append(geometry)
            samples.append({'width':width,'time_ms':time_ms,'labels':[g['label'] for g in geometry]})
        for ship in range(4):
            assert len({frame[ship]['motion'] for frame in frames})>1,(width,ship,'boat does not bob')
            for coordinate in ('left','right','labelTop'):
                values=[frame[ship][coordinate] for frame in frames]
                assert max(values)-min(values)<.3,(width,ship,coordinate,'label moves with boat')
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('.ships .ship').evaluate_all(
            "els=>els.every(e=>e.getAnimations({subtree:true}).length===0)"
        )
        page.emulate_media(reduced_motion='no-preference')
    return {'samples':samples,'issues':[]}


def check_artwork_spacing(page):
    """The logo variants must not collide with copy or the scene disclosure."""
    samples=[]
    for width,height in ((375,667),(375,812),(768,1024),(821,900),(1024,900),(1440,1000)):
        page.set_viewport_size({'width':width,'height':height})
        page.goto('about:blank')
        page.goto((ROOT/'docs'/'index.html').as_uri())
        page.wait_for_timeout(100)
        variants=[]
        for sid in ('hero',*(f'sec-{n}' for n in range(1,7))):
            scene=page.locator('#'+sid+' .scene-intro')
            for p in (0,.5,1):
                scene.evaluate("""(e,p)=>scrollTo({
                  top:scrollY+e.getBoundingClientRect().top+Math.max(0,e.clientHeight-e.querySelector('.scene-stage').offsetHeight)*p,
                  behavior:'instant'
                })""",p)
                page.wait_for_timeout(70)
                geometry=scene.evaluate("""e=>{
                  const rect=n=>n.getBoundingClientRect();
                  const copy=rect(e.querySelector('.scene-copy'));
                  const footer=rect(e.querySelector('.scene-bottom'));
                  const root=e.querySelector('.layer-art');
                  const artwork=rect(root);
                  const stage=rect(e.querySelector('.scene-stage'));
                  const overlap=(a,b)=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top;
                  const rendered=[...root.querySelectorAll('.data-plane,.brand-scene')].map(rect);
                  const contains=(outer,inner)=>inner.left>=outer.left-1 && inner.right<=outer.right+1 &&
                    inner.top>=outer.top-1 && inner.bottom<=outer.bottom+1;
                  const logoUse=[...root.querySelectorAll('use[href="#plimsoll-emblem"]')];
                  const visibleLogo=logoUse.length>0 && logoUse.every(u=>{
                    const bounds=rect(u);let opacity=1;
                    for(let node=u;node;node=node.parentElement){
                      const style=getComputedStyle(node);
                      if(style.display==='none'||style.visibility==='hidden') return false;
                      opacity*=Number(style.opacity);
                    }
                    return bounds.width>0 && bounds.height>0 && opacity>.05 && contains(stage,bounds) &&
                      contains(rect(u.ownerSVGElement),bounds);
                  });
                  return {variant:root.dataset.artwork,overlap:overlap(copy,artwork)||rendered.some(r=>overlap(copy,r)),
                    footerOverlap:overlap(footer,artwork)||rendered.some(r=>overlap(footer,r)),
                    left:Math.min(artwork.left,...rendered.map(r=>r.left)),right:Math.max(artwork.right,...rendered.map(r=>r.right)),
                    visibleLogo,docWidth:document.documentElement.scrollWidth};
                }""")
                assert not geometry['overlap'],(width,height,sid,p,geometry)
                assert not geometry['footerOverlap'],(width,height,sid,p,geometry)
                assert geometry['left']>=0 and geometry['right']<=width,(width,height,sid,p,geometry)
                assert geometry['docWidth']<=width and geometry['visibleLogo'],(width,height,sid,p,geometry)
            variants.append(geometry['variant'])
        assert len(set(variants))==7,variants
        samples.append({'width':width,'height':height,'variants':variants})
    return {'samples':samples,'issues':[]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=("replay", "transitions", "review", "fleet", "artwork", "all"), default="all")
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--output", type=Path, help="Optional JSON result file")
    parser.add_argument("--screenshots", type=Path, help="Optional directory for visual QA")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = (playwright.chromium.launch(executable_path=str(CHROME), headless=True)
                   if args.browser == "chromium" else playwright.webkit.launch(headless=True))
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        context.on("page", lambda p: p.on("pageerror", lambda error: errors.append(str(error))))
        context.on("request", lambda request: requests.append(request.url))
        context.route("https://**/*", lambda route: route.abort())
        context.route("http://**/*", lambda route: route.abort())
        page = context.new_page()
        page.goto((ROOT / "docs" / "index.html").as_uri())
        result: dict = {"browser": args.browser}
        if args.only in ('fleet','all'):
            result['fleet']=check_fleet_layout(page)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto('about:blank')
            page.goto((ROOT/'docs'/'index.html').as_uri())
        if args.only in ('artwork','all'):
            result['artwork']=check_artwork_spacing(page)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto('about:blank')
            page.goto((ROOT/'docs'/'index.html').as_uri())
        if args.only in ("replay", "all"):
            result["replay"] = check_replay(page)
        if args.only in ("transitions", "all"):
            result["transitions"] = check_transitions(page)
        if args.only in ("review", "all"):
            result['review_regressions']=check_review_regressions(page)
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
                assert static_page.locator('.scene-stage').evaluate_all(
                    "els=>els.every(e=>getComputedStyle(e).position!=='sticky')"
                ), "fallback still pins scenes"
                assert static_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                result[mode] = "passed"
                fallback.close()
            result['responsive_scenes']=check_responsive_scenes(page)
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
