"""Original, offline visual language for the fixture-backed report.

The supplied reference video guides composition and motion, not assets or claims.
All meshes are decorative, generated here, and labelled as visual metaphors.
"""

from __future__ import annotations

import html
import math


CHAPTERS = (
    ("The verdict", "One question.<br>One <em>answer.</em>",
     "Four providers. Two recorded runs. No disagreement on completeness or freshness for the pinned queries.",
     "01 / AGREEMENT", "aligned"),
    ("The findings", "Below the<br><em>surface.</em>",
     "The answers agree. The interfaces do not. Explore the filters, pagination rules, and timestamps behind the result.",
     "02 / INTERFACES", "separated"),
    ("The method", "Same question.<br><em>Every time.</em>",
     "Comparable predicates. Exact event identities. Complete pagination. A verdict built from the same test, not assumptions.",
     "03 / METHOD", "flow"),
    ("The limits", "Know where<br>the evidence<br><em>ends.</em>",
     "A dated snapshot is not continuous monitoring. Every conclusion has a boundary. These are ours.",
     "04 / BOUNDARIES", "boundary"),
    ("The evidence", "Nothing<br>without<br><em>proof.</em>",
     "The recorded responses, observation rows, and verdict computation remain open to inspection.",
     "05 / PROVENANCE", "archive"),
    ("The correction", "Better evidence.<br><em>Better answers.</em>",
     "An earlier interpretation was wrong. The record is preserved, the claim corrected, and the evidence left legible.",
     "06 / CORRECTION", "resolved"),
)


def mesh_definitions():
    """A reusable original point mesh: shapes are not provider measurements."""
    lines, dots = [], []
    for row in range(17):
        coords = []
        for col in range(31):
            x = 24 + col * 15.2
            y = 30 + row * 17.5 + math.sin(col * .21 + row * .13) * 13
            y += math.cos(col * .12 - row * .19) * 7
            coords.append(f"{x:.1f},{y:.1f}")
            radius = .8 + .35 * math.sin(row * .31 + col * .21) ** 2
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}"/>')
        lines.append('<polyline points="' + ' '.join(coords) + '"/>')
    cloud = []
    for row in range(22):
        v = row / 21
        for col in range(40):
            angle = col / 40 * math.tau
            radius = 100 + 45 * math.sin(v * math.pi) + 10 * math.cos(angle * 3 + v * 7)
            x = 260 + math.cos(angle) * radius
            y = 24 + v * 310 + math.sin(angle) * 34
            opacity = .15 + .72 * (math.sin(angle) + 1) / 2
            cloud.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1" opacity="{opacity:.2f}"/>')
    return (
        '<svg class="mesh-definitions" width="0" height="0" aria-hidden="true" '
        'focusable="false" xmlns="http://www.w3.org/2000/svg"><defs>'
        '<symbol id="mesh-surface" viewBox="0 0 520 360">'
        '<g fill="none" stroke="currentColor" stroke-width=".45" opacity=".32">'
        + ''.join(lines) + '</g><g fill="currentColor">' + ''.join(dots) + '</g></symbol>'
        '<symbol id="particle-surface" viewBox="0 0 520 360"><g fill="currentColor">'
        + ''.join(cloud) + '</g></symbol></defs></svg>'
    )


def layer_art(mode):
    planes = ''.join(
        f'<svg class="data-plane plane-{i}" style="--level:{i - 1.5}" '
        'viewBox="0 0 520 360" focusable="false">'
        '<rect class="plane-edge" x="7" y="7" width="506" height="346" rx="2"/>'
        '<use href="#mesh-surface"/></svg>'
        for i in range(4)
    )
    return (
        f'<div class="layer-art" data-mode="{html.escape(mode)}" aria-hidden="true">'
        '<div class="art-grid"></div><div class="art-orbit"></div>'
        '<svg class="particle-field" viewBox="0 0 520 360" focusable="false">'
        '<use href="#particle-surface"/></svg>'
        f'<div class="layer-stack">{planes}</div>'
        '<div class="art-axis axis-x"></div><div class="art-axis axis-y"></div>'
        '<span class="art-cross cross-a">+</span><span class="art-cross cross-b">+</span>'
        '<span class="art-coordinate">PLM / STRUCTURE STUDY</span></div>'
    )


def scene_intro(index, date, verdict=None):
    if index == 0:
        eyebrow, title = "SUI MAINNET / A PREMISE SPIKE", "One chain.<br>Four providers.<br><em>One answer?</em>"
        description = "Do Sui mainnet RPC providers disagree on event data? A recorded experiment, examined layer by layer."
        label, mode = "FIELD REPORT / " + date, "cloud"
        heading = "h1"
        detail = (f'<a class="scene-cta" href="#sec-1">Explore the findings <span aria-hidden="true">↘</span></a>'
                  f'<span class="hero-verdict">Recorded verdict <b>{html.escape(verdict or "")}</b></span>')
        buoy = '<svg class="buoy" viewBox="0 0 100 100" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="4"><line x1="4" y1="50" x2="96" y2="50"/><circle cx="50" cy="50" r="26"/></svg>'
    else:
        eyebrow, title, description, label, mode = CHAPTERS[index - 1]
        heading, detail, buoy = "h2", "", ""
    return (
        f'<div class="scene-intro" data-scene="{index}" data-mode="{mode}">'
        '<div class="scene-stage">'
        '<div class="scene-copy">'
        f'<p class="scene-eyebrow">{html.escape(eyebrow)}</p>'
        f'<{heading} class="scene-title">{title}</{heading}>'
        f'<p class="scene-description">{html.escape(description)}</p>'
        f'<div class="scene-actions">{detail}</div></div>'
        f'{layer_art(mode)}{buoy}'
        '<div class="scene-bottom">'
        f'<span>{html.escape(label)}</span><span class="scene-metaphor">Visual metaphor · not a measurement</span>'
        '<span class="scene-scroll" aria-hidden="true">SCROLL TO EXPLORE ↓</span>'
        '</div></div></div>'
    )


def site_header(logo, date):
    return (
        '<header class="site-header"><a class="site-brand" href="#hero" aria-label="Plimsmark — back to top">'
        + logo + '<span>plimsmark<span class="brand-period">.</span></span></a>'
        '<div class="header-meta"><span>SUI MAINNET</span><span>INDEPENDENT PREMISE SPIKE</span></div>'
        f'<a class="header-evidence" href="#sec-5">Recorded evidence <span aria-hidden="true">↗</span></a>'
        '<div class="reading-progress" aria-hidden="true"><span></span></div></header>'
    )


THEME_CSS = r"""
/* Reference-inspired industrial editorial shell; original generated meshes. */
:root{--ink:#ecf3f8;--muted:#9fb6c9;--accent:#77d8ed;--accent-ink:#071d30;
  --link:#a6e5f6;--line:rgba(162,204,228,.2);--code-bg:rgba(150,194,221,.08);
  --card:rgba(150,194,221,.035);--sea0:#07192e;--sea1:#091e36;--sea2:#07182c;
  --sea3:#0a233c;--sea4:#e3eef3;--sea5:#f3f7f9;--sea6:#071a2f}
body{background:#07192e;color:var(--ink);font-family:"Helvetica Neue",Arial,sans-serif;
  font-weight:400;font-size:17px;line-height:1.7}
::selection{background:#7dd5e4;color:#081d30}
strong,h3,th{color:var(--ink)}
em{font-style:normal;color:var(--accent)}
code{border-radius:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.mesh-definitions{position:absolute;pointer-events:none}
.site-header{position:fixed;inset:0 0 auto;z-index:40;height:88px;display:flex;align-items:center;
  justify-content:space-between;gap:24px;padding:0 clamp(24px,4vw,72px);color:#eef6fb;
  background:#07192e;transition:color .35s,background .35s}
.site-brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit;
  font-size:27px;letter-spacing:-1.1px;font-weight:600}
.site-brand .mark{width:34px;height:34px}
.brand-period{color:#78dced}
.header-meta{display:flex;gap:24px;font-size:9px;letter-spacing:.16em;color:#adbed1}
.header-evidence{display:flex;align-items:center;gap:20px;min-height:44px;padding:6px 17px;
  border:1px solid #cadce7;color:#edf7fc;text-decoration:none;font-size:11px;letter-spacing:.02em}
.header-evidence:hover{background:#e5f1f8;color:#0a2238}
.site-header[data-light="true"]{background:#e3eef3;color:#122e46}
.site-header[data-light="true"] .header-meta{color:#466073}
.site-header[data-light="true"] .header-evidence{color:#102c42;border-color:#718b9b}
.reading-progress{position:absolute;left:0;bottom:0;right:0;height:1px;background:rgba(120,164,195,.18)}
.reading-progress span{display:block;height:100%;background:#77d8ed;transform:scaleX(var(--reading,0));transform-origin:left}
.depth{position:relative;isolation:isolate;padding:0 0 clamp(90px,12vh,160px);scroll-margin-top:0}
/* Keep report copy beyond the desktop rail without moving wide-screen columns. */
.depth>.inner{position:relative;z-index:2;max-width:1080px;margin:0 auto;padding:60px 46px 0;
  padding-left:max(46px,calc(150px - max(0px,(100vw - 1080px)/2)))}
.depth>.inner>h2{font-size:clamp(24px,3vw,39px);line-height:1.2;font-weight:450;
  letter-spacing:-1.2px;margin:0 0 36px;max-width:860px}
h2 .n{font-size:12px;font-weight:500;letter-spacing:.05em;border-radius:0;padding:6px 9px}
h3{font-size:1.22rem;line-height:1.4;font-weight:500;letter-spacing:-.3px;margin:2.5em 0 .75em}
.depth>.inner>p{max-width:800px}
.lede{font-size:1.2rem;line-height:1.7}
.wave{display:none}
#hero{display:block;min-height:0;padding:0;overflow:visible;background:#07192e}
#hero .buoy{position:absolute;right:5%;bottom:19%;width:66px;height:66px;color:#a3dce7;
  filter:none;opacity:.55;z-index:1}
.js-anim #hero .buoy{animation:none}
.scene-intro{--scene-progress:0;--scene-spin:-30deg;--scene-tilt:60deg;--scene-gap:36px;
  --scene-scale:1;--scene-lift:0px;--scene-copy-y:0px;--cloud-opacity:.08;--cloud-scale:1;
  position:relative;height:148vh;min-height:950px;border-bottom:1px solid var(--line)}
.scene-stage{height:100vh;min-height:600px;position:sticky;top:0;overflow:hidden;display:grid;
  grid-template-columns:44% 56%;align-items:center;padding:96px max(100px,8.5vw) 100px;
  padding-left:max(150px,8.5vw)}
.scene-stage::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(ellipse at 77% 53%,rgba(38,103,147,.15),transparent 59%)}
.scene-copy{position:relative;z-index:3;max-width:580px;transform:translate3d(0,var(--scene-copy-y),0)}
.scene-eyebrow{font-size:10px;font-weight:500;letter-spacing:.19em;text-transform:uppercase;
  margin:0 0 28px;color:var(--muted)}
.scene-title{display:block;font-family:"Arial Narrow","Helvetica Neue",Arial,sans-serif;font-weight:450;
  font-size:clamp(54px,5.8vw,102px);line-height:1.01;letter-spacing:-.065em;margin:0 0 27px;color:var(--ink)}
#hero .scene-title{font-size:clamp(60px,6.6vw,116px)}
.scene-title em{font-weight:400;color:var(--accent)}
.scene-description{max-width:36ch;font-size:clamp(14px,1.2vw,18px);line-height:1.75;color:var(--muted);margin:0}
.scene-actions{display:flex;align-items:flex-start;gap:17px;flex-direction:column;margin-top:32px}
.scene-actions:empty{display:none}
.scene-cta{display:flex;gap:48px;align-items:center;text-decoration:none;background:#deecf4;color:#0a253e;
  min-height:48px;padding:9px 20px;font-size:12px;border:1px solid #f2f8fc}
.scene-cta:hover{background:#fff}
.hero-verdict{color:#9fb6c9;font-size:10px;letter-spacing:.08em;text-transform:uppercase}
.hero-verdict b{margin-left:12px;color:#93e1ed;font-weight:500}
.scene-bottom{position:absolute;bottom:36px;left:max(150px,8.5vw);right:max(54px,5vw);display:flex;
  justify-content:space-between;gap:14px;font:9px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;color:var(--muted);font-size:10px}
.scene-metaphor{opacity:.8}
.scene-scroll{color:var(--accent)}
.layer-art{position:relative;width:clamp(430px,47vw,920px);height:clamp(420px,55vh,720px);
  margin-left:0;perspective:1300px;z-index:1;color:#82d5ed;pointer-events:none;
  transform:translate3d(0,var(--scene-lift),0) scale(var(--scene-scale))}
.layer-stack{position:absolute;inset:17% 0;transform-style:preserve-3d;
  transform:rotateX(var(--scene-tilt)) rotateZ(var(--scene-spin));}
.data-plane{position:absolute;inset:0;width:100%;height:100%;overflow:visible;
  transform:translateZ(calc(var(--level) * var(--scene-gap)));backface-visibility:visible;
  filter:drop-shadow(0 1px 8px rgba(82,161,200,.12));}
.plane-edge{fill:rgba(8,29,49,.27);stroke:currentColor;stroke-width:.65}
.plane-0{color:#275e91}.plane-1{color:#4daada}.plane-2{color:#b6eff3}.plane-3{color:#75d9d7}
.art-grid{position:absolute;inset:3% -3%;border:1px solid rgba(150,202,223,.07);
  background-image:linear-gradient(rgba(96,153,182,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(96,153,182,.045) 1px,transparent 1px);
  background-size:54px 54px;transform:rotate(-9deg);opacity:.6}
.art-orbit{position:absolute;inset:12% 10%;border:1px solid rgba(126,197,224,.14);border-radius:50%;
  transform:rotate(-30deg) scaleY(.55)}
.particle-field{position:absolute;inset:-8% -4%;width:108%;height:116%;color:#a2e7ef;
  opacity:var(--cloud-opacity);transform:scale(var(--cloud-scale)) rotate(calc(var(--scene-progress) * 18deg));}
.art-axis{position:absolute;background:rgba(127,192,222,.19)}
.axis-x{width:88%;height:1px;left:5%;top:55%;transform:rotate(-22deg)}
.axis-y{width:1px;height:84%;left:55%;top:8%;transform:rotate(-22deg)}
.art-cross{position:absolute;font:18px ui-monospace,monospace;color:#6a8ca8}
.cross-a{left:9%;top:6%}.cross-b{right:4%;bottom:8%}
.art-coordinate{position:absolute;right:1%;bottom:0;font:8px ui-monospace,monospace;letter-spacing:.17em;color:var(--muted)}
.scene-intro[data-mode="cloud"]{--cloud-opacity:.62;--scene-gap:12px}
[data-mode="cloud"] .layer-stack{opacity:.5}
.scene-intro[data-mode="separated"]{--scene-gap:82px;--scene-spin:-22deg}
.scene-intro[data-mode="flow"]{--scene-gap:48px;--scene-spin:26deg;--scene-tilt:68deg}
.scene-intro[data-mode="boundary"]{--scene-gap:18px;--scene-spin:-42deg}
.scene-intro[data-mode="archive"]{--scene-gap:62px;--scene-spin:16deg}
.scene-intro[data-mode="resolved"]{--scene-gap:14px;--scene-spin:-22deg}
/* Paper chapters replace the flat teal bands with a pronounced dark/light passage. */
.light-chapter{--ink:#17324a;--muted:#4a6476;--accent:#126c84;--accent-ink:#f3f7f9;
  --link:#176179;--line:rgba(21,56,78,.19);--code-bg:rgba(24,69,95,.06);--card:rgba(36,72,95,.025);
  color:var(--ink);color-scheme:light}
.light-chapter .scene-stage::before{background:radial-gradient(ellipse at 77% 53%,rgba(104,170,183,.1),transparent 60%)}
.light-chapter .plane-edge{fill:rgba(218,234,242,.38)}
.light-chapter .plane-0{color:#2d5385}.light-chapter .plane-1{color:#37809c}
.light-chapter .plane-2{color:#306176}.light-chapter .plane-3{color:#328c91}
.light-chapter .art-grid{border-color:rgba(33,84,111,.13)}
.light-chapter .art-axis{background:rgba(37,96,127,.18)}
.light-chapter .art-orbit{border-color:rgba(30,101,132,.18)}
.light-chapter strong,.light-chapter h3{color:var(--ink)}
.gauge{left:25px}
.gauge .dot{width:8px;height:8px;border-width:1px}
.gauge ol::before{left:3px;top:22px;bottom:22px;width:1px}
.gauge .lbl{font-size:9px;letter-spacing:.08em;text-transform:uppercase}
.gauge a{min-width:44px;gap:12px}
.gauge[data-light="true"]{--muted:#557185;--line:rgba(41,80,107,.25);--accent:#176e8b}
.gauge[data-light="true"] a.on{color:#18364f}
.terminal,.diagram,.sonar,.timeline,.route,.latency,.pipeline,.amendment{border-radius:2px;
  padding:26px;margin:1.8em 0;background:var(--card);border-color:var(--line)}
.terminal{padding:0;background:#061425}
.term-bar,.term-note{padding:14px 20px}
.term-body{padding:20px;font-size:.82rem}
.caption,figcaption.caption{text-align:left;font-size:.8rem;line-height:1.8;max-width:90ch}
.lat-title{font-size:1rem;font-weight:500}
.js-anim .reveal .pipe-node,.js-anim .reveal.shown .pipe-node{opacity:1;filter:none;transition:none}
.sonar-scope{max-width:640px;border-radius:2px;background:#07192e;padding:20px;border-color:rgba(138,198,220,.24)}
.pg-title{margin-bottom:18px}
.pg-controls button,.dg-box,.pipe-node,.tablewrap{border-radius:2px}
.pg-controls button,.pg-slider{min-height:46px}
.pg-readout{font-size:.92rem}
.sonar-read{font-size:.8rem;text-align:left}
.manifest{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 36px}
.manifest-card{padding:24px 0;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent;
  transition:background .2s,transform .2s}
.manifest-card:hover,.manifest-card:focus-visible{background:rgba(46,117,145,.055);transform:translateX(5px)}
.mf-file{color:var(--ink);font-size:.85rem;overflow-wrap:anywhere}
.mf-label{font-size:.86rem;margin-top:4px}
.mf-path{color:var(--accent);max-height:none;opacity:.7;margin-top:5px;font-size:.69rem;overflow-wrap:anywhere}
.loadline{padding:12px 0}
.ll-mark{padding:20px 0;gap:18px}
.ll-text{font-size:1.02rem;line-height:1.7}
.ll-disc{margin-right:20px;width:64px;height:64px}
.ll-tick{background:var(--accent)}
.light-chapter .ll-marks::before{background:#77a5b6}
.amendment{border-left:1px solid var(--line)}
.amend-tag{border-radius:0;transform:none}
.stamp{border-radius:2px}
.type-details{display:grid;grid-template-columns:auto 1fr;gap:12px 20px;align-items:start}
.type-details dt{font:11px/1.8 ui-monospace,monospace;color:var(--accent);padding-top:5px}
.type-details dd{margin:0;min-width:0}
.type-details code{display:block;padding:6px 10px;overflow-wrap:anywhere}
/* Scroll-scrubbed block motion: no whole-section hiding and no CSS time delay. */
.reveal{opacity:1;transform:none}
.js-anim .motion-item{opacity:var(--item-opacity,1);
  transform:translate3d(0,var(--item-y,0px),0) scale(var(--item-scale,1));transform-origin:50% 0;
  transition:none}
.js-anim .motion-item:focus-within{opacity:1;transform:none}
footer{max-width:1080px;padding:65px 46px 100px;border-top:1px solid var(--line);font-size:.8rem}
@media (min-width:1700px){.scene-stage{padding-left:12vw}.scene-bottom{left:12vw}.scene-title{font-size:110px}}
@media (max-width:1100px) and (min-width:821px){
  .scene-stage{padding-left:150px;padding-right:40px;grid-template-columns:46% 54%}
  .scene-title,#hero .scene-title{font-size:60px}.layer-art{width:530px}
  .art-coordinate{display:none}
  .header-meta span:last-child{display:none}.scene-bottom{left:150px}}
@media (max-width:820px){
  body{font-size:16px}.site-header{height:70px;padding:0 20px;gap:15px}
  .site-brand{font-size:24px}.site-brand .mark{width:27px;height:27px}.header-meta{display:none}
  .header-evidence{font-size:10px;gap:8px;padding:4px 10px}
  .scene-intro{height:132vh;min-height:900px}
  .scene-stage{height:100svh;min-height:670px;display:block;padding:110px 25px 90px}
  .scene-copy{max-width:500px}.scene-title,#hero .scene-title{font-size:clamp(49px,10vw,74px);line-height:1.02;
    letter-spacing:-.055em;margin-bottom:20px}
  .scene-eyebrow{font-size:9px;margin-bottom:18px}.scene-description{font-size:13px;max-width:32ch;line-height:1.65}
  .scene-actions{margin-top:21px;gap:10px}.scene-cta{min-height:44px;padding:7px 14px;gap:35px;font-size:11px}
  .hero-verdict{font-size:8px}
  .layer-art{position:absolute;width:78vw;height:39vh;min-height:250px;right:-4vw;bottom:94px;margin:0}
  #hero .layer-art{right:-11vw;bottom:62px;width:84vw;opacity:.8}
  .layer-stack{inset:20% 0}.art-grid{opacity:.3}.art-coordinate{font-size:7px}
  .art-coordinate,.art-cross{display:none}
  .scene-bottom{left:25px;right:25px;bottom:76px;font-size:8px;letter-spacing:.02em;gap:8px}
  .scene-metaphor{max-width:130px;text-align:right}.scene-scroll{display:none}
  #hero .buoy{right:19px;bottom:24%;width:40px;height:40px}
  .depth{padding:0 0 65px}.depth>.inner{padding:38px 22px 0}
  .depth>.inner>h2{font-size:28px;letter-spacing:-.9px;margin-bottom:26px}
  h3{font-size:1.08rem;margin-top:2em}.lede{font-size:1.08rem}
  .gauge{left:0;right:0;bottom:0;top:auto;z-index:45;transform:none;background:#06182cf5;backdrop-filter:none}
  .gauge[data-light="true"]{background:#e5eff6fa;border-top-color:#afc1d0}
  .gauge .lbl{font-size:8px;letter-spacing:0;text-transform:none}
  .gauge a{gap:5px;padding:5px 1px}.gauge .dot{width:6px;height:6px}
  .terminal,.diagram,.sonar,.timeline,.route,.latency,.pipeline,.amendment{padding:16px;margin:1.4em 0}
  .terminal{padding:0}.term-bar,.term-note,.term-body{padding:12px}
  .sonar-scope{padding:10px}.pg-readout{font-size:.8rem}.pg-title{font-size:.83rem}
  .caption,figcaption.caption{font-size:.79rem}.manifest{grid-template-columns:1fr}
  .ll-rail{gap:9px}.ll-disc{width:35px;height:35px;margin-right:0}.ll-mark{gap:8px;padding:14px 0}
  .ll-text{font-size:.93rem}.type-details{grid-template-columns:1fr;gap:4px}.type-details dd{margin-bottom:10px}
  footer{padding:50px 22px 110px}
}
@media (max-width:820px) and (max-height:750px){
  .scene-stage{min-height:720px}.layer-art{bottom:80px;height:280px;opacity:.6}
  .scene-bottom{bottom:55px}.scene-description{font-size:12px}}
.scene-intro[data-unpinned="true"]{height:auto;min-height:0}
.scene-intro[data-unpinned="true"]>.scene-stage{position:relative}
/* No script tracks chapter colours: keep the fallback rail on its own navy surface. */
html:not(.js-anim) .gauge:not([data-light="true"]){background:#07192e}
html:not(.js-anim) .scene-intro{height:auto;min-height:0}
html:not(.js-anim) .scene-stage{position:relative}
html:not(.js-anim) .scene-copy,html:not(.js-anim) .layer-art{transform:none}
@media (prefers-reduced-motion:reduce){
  .scene-intro{height:auto;min-height:0}.scene-stage{position:relative}
  .scene-copy,.layer-art,.motion-item{transform:none!important;opacity:1!important}
}
@media print{
  .site-header,.gauge,.scene-intro,.mesh-definitions{display:none}
  body,.depth{background:white!important;color:black!important}
  .depth>.inner{padding:20px 0}.motion-item{opacity:1!important;transform:none!important}
}
"""


MOTION_JS = r"""
  // Original scene choreography follows the scroll position, not a one-shot fade.
  function setupSceneMotion(){
    var intros=[].slice.call(document.querySelectorAll('.scene-intro'));
    var elements=[].slice.call(document.querySelectorAll('.depth > .inner > *'));
    var header=document.querySelector('.site-header');
    var nav=document.querySelector('.gauge');
    var scenes=[], blocks=[], measuredWidth=0, measuredHeight=0;
    var modes={cloud:[66,-28,12],aligned:[59,-32,30],separated:[61,-22,82],
      flow:[68,26,48],boundary:[62,-42,18],archive:[56,16,62],resolved:[60,-22,14]};
    function clamp(value){return Math.max(0,Math.min(1,value));}
    function topOf(el){var top=0;while(el){top+=el.offsetTop;el=el.offsetParent;}return top;}
    elements.forEach(function(el){el.classList.add('motion-item');});
    function measure(){
      measuredWidth=window.innerWidth;measuredHeight=window.innerHeight;
      // Oversized stages scroll normally; remove their pin space before measuring tops.
      intros.forEach(function(el){
        el.dataset.unpinned=String(reduce||el.querySelector('.scene-stage').offsetHeight>measuredHeight);
      });
      scenes=intros.map(function(el){
        var stage=el.querySelector('.scene-stage'),copy=el.querySelector('.scene-copy');
        return {el:el,top:topOf(el),height:el.clientHeight,stageHeight:stage.offsetHeight,
          copyTravel:Math.max(0,Math.min(38,copy.offsetTop-header.offsetHeight-8))};
      });
      blocks=elements.map(function(el){return {el:el,top:topOf(el),height:el.offsetHeight};});
    }
    function update(active){
      if(window.innerWidth!==measuredWidth||window.innerHeight!==measuredHeight) measure();
      var y=window.scrollY,vh=window.innerHeight;
      var max=Math.max(1,document.documentElement.scrollHeight-vh);
      header.style.setProperty('--reading',clamp(y/max).toFixed(4));
      var light=active===3||active===4;
      header.dataset.light=String(light);nav.dataset.light=String(light);
      scenes.forEach(function(scene){
        var el=scene.el,range=Math.max(0,scene.height-scene.stageHeight);
        var p=reduce||!range?0:clamp((y-scene.top)/range);
        var base=modes[el.dataset.mode],exit=reduce||!range?0:clamp((y-scene.top-range)/(vh*.8));
        var state=p.toFixed(4)+':'+exit.toFixed(4);
        if(scene.state===state) return;
        scene.state=state;
        el.style.setProperty('--scene-progress',p.toFixed(4));
        el.style.setProperty('--scene-spin',(base[1]+p*42).toFixed(2)+'deg');
        el.style.setProperty('--scene-tilt',(base[0]-p*19).toFixed(2)+'deg');
        el.style.setProperty('--scene-gap',(base[2]+Math.sin(p*Math.PI)*75).toFixed(2)+'px');
        el.style.setProperty('--scene-scale',(1+p*.14).toFixed(4));
        el.style.setProperty('--scene-lift',(-p*26-exit*35).toFixed(2)+'px');
        el.style.setProperty('--scene-copy-y',(-Math.min(p*38,scene.copyTravel)).toFixed(2)+'px');
        el.style.setProperty('--cloud-opacity',(el.dataset.mode==='cloud'?.72*(1-p):.03).toFixed(4));
        el.style.setProperty('--cloud-scale',(1+p*.38).toFixed(4));
      });
      blocks.forEach(function(block){
        var top=block.top-y,entry=reduce?1:clamp((vh*.94-top)/(vh*.4));
        if(block.entry===entry) return;
        block.entry=entry;
        var eased=1-Math.pow(1-entry,3);
        block.el.style.setProperty('--item-y',((1-eased)*78).toFixed(2)+'px');
        block.el.style.setProperty('--item-opacity',(.12+eased*.88).toFixed(4));
        block.el.style.setProperty('--item-scale',(.975+eased*.025).toFixed(4));
      });
    }
    measure();
    if(window.ResizeObserver){
      var observer=new ResizeObserver(function(){measure();onScroll();});
      observer.observe(document.querySelector('main'));
    }
    return {update:update,measure:measure};
  }
  var sceneMotion=setupSceneMotion();
"""
