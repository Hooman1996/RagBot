# Step 2 logout control verification

This local verification used rendered HTML from FastAPI `TestClient` and the
scoped CSS. No browser binary or screenshot renderer is installed on the Ubuntu
workspace, so pixel-level screenshots and a live interaction pass in the
forwarded browser are still unavailable. The existing server answered HTTP 200
at `http://localhost:7000/`; that does not prove it has reloaded this branch.

| State | Verified from local rendering and CSS |
| --- | --- |
| Chat desktop | One sign-out button is inside topbar actions with theme and language controls. |
| Analytics desktop | One sign-out button is inside topbar actions with theme, range and refresh controls; Knowledge links to `/knowledge-base`. |
| KB desktop | One Persian sign-out button is inside the header control group; the chat return link is shown only when permitted. |
| Narrow (700px, 420px breakpoints) | Header actions wrap, status chip yields space, KB header wraps, and the sign-out text collapses at 420px while its accessible name remains. |
| RTL | Chat `body.rtl` directs the controls in RTL; KB has `dir="rtl"`; the sign-out SVG mirrors in RTL. |
| Dark/light | The default dark styling and `body.light-mode` override use the existing theme variables. KB currently has only its existing dark theme. |
| Keyboard | Each button is `type="button"`, has a title and accessible name, and uses a visible `:focus-visible` outline. |

`tests/test_web_permissions.py` checks the three rendered header groups, exactly
one button on each, icon and labels, permission-aware links, and key responsive,
RTL, light, and focus rules. A manual forwarded-browser check should still be
done before review approval for actual geometry, contrast, and interaction.
