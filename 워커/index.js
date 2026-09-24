// 서아 깨우기 워커 — 20분마다 깃허브 액션(seoa.yml)을 깨운다 (2026-09-25 사장님 지시 "클라우드 호출이 1번").
// 깃허브 자체 cron 은 2~6시간씩 미뤄져서 믿을 수 없다.
// **깨우기 전에 R2 심장박동을 먼저 본다.** PC 가 20분 안에 살아 있었으면 깃허브를 두드리지 않는다
// (저장소가 공개라 실행 화면이 누구나 보이고, 헛도는 실행을 줄이려고). 못 읽으면 그냥 깨운다 — 안 깨우는 쪽이 더 위험하다.
// 팔자오빠 워커(shorts-wake)와 **따로다.** 저장소도 비밀값도 다르다.
const 조용분 = 20;

async function pcAlive(env) {
  if (!env.STORE) return null;
  try {
    const obj = await env.STORE.get("seoa/심장박동.json");
    if (!obj) return false;
    const hb = JSON.parse(await obj.text());
    // 심장박동은 한국 시간 문자열 "YYYY-MM-DD HH:MM:SS"
    const at = Date.parse(hb["때"].replace(" ", "T") + "+09:00");
    const min = (Date.now() - at) / 60000;
    console.log(`PC 심장박동 ${min.toFixed(0)}분 전`);
    return min < 조용분;
  } catch (e) {
    console.log(`심장박동 못 읽음: ${e}`);
    return null;
  }
}

async function wake(env, wf) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${wf}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN.trim()}`,
      accept: "application/vnd.github+json",
      "content-type": "application/json",
      "user-agent": "seoa-wake",
    },
    body: JSON.stringify({ ref: env.GITHUB_REF || "master" }),
  });
  const ok = r.status === 204;
  console.log(`${wf}: ${ok ? "깨움" : "실패 HTTP " + r.status + " " + (await r.text().catch(() => "")).slice(0, 120)}`);
  return ok;
}

async function wakeAll(env) {
  if (!env.GITHUB_TOKEN) { console.log("GITHUB_TOKEN 없음"); return {}; }
  const alive = await pcAlive(env);
  if (alive === true) { console.log("PC 살아 있음 → 안 깨움"); return { skipped: true }; }
  const out = {};
  for (const wf of (env.WORKFLOWS || "").split(",").map((s) => s.trim()).filter(Boolean)) {
    out[wf] = await wake(env, wf).catch((e) => { console.log(`${wf}: ${e}`); return false; });
  }
  return out;
}

export default {
  async scheduled(_ctrl, env, ctx) { ctx.waitUntil(wakeAll(env)); },
  // 주소로 열면 상태만 보여 준다 (깨우진 않는다 — 아무나 눌러서 깃허브를 두드리지 못하게)
  async fetch(_req, env) {
    const alive = await pcAlive(env);
    return new Response(JSON.stringify({ worker: "seoa-wake", repo: env.GITHUB_REPO, every: "20분", token: !!env.GITHUB_TOKEN, pc_alive: alive }), {
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  },
};
