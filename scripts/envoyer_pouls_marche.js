#!/usr/bin/env node
// Pouls du Marché BRVM — envoi automatique quotidien (email Brevo + notification push OneSignal), 15h15 GMT.
// Aucune dépendance : Node 18+ (fetch intégré).
//
// Variables d'environnement (secrets GitHub) :
//   BREVO_API_KEY, BREVO_LIST_ID, ONESIGNAL_APP_ID, ONESIGNAL_REST_API_KEY
// Options : FORCER=1 (ignore les contrôles de date et d'anti-doublon, pour les tests)
//           APERCU=1 (ne rien envoyer : écrit apercu-pouls.html et affiche la notification)
//           BREVO_SENDER_EMAIL (facultatif : expéditeur ; sinon le premier expéditeur validé du compte Brevo)
//           BREVO_FORM_URL (facultatif : lien public du formulaire d'inscription Brevo, affiché dans l'application)
const fs = require("fs");
const path = require("path");

const RACINE = path.resolve(__dirname, "..");
const APP_URL = "https://horizonbourse12-alt.github.io/le_Semeur.app/";
const VERT = "#1C4330", OR = "#B4842A", OR_CLAIR = "#F6EFDD", BLANC = "#FFFFFF";
const E = process.env;
const FORCER = E.FORCER === "1" || E.FORCER === "true";
const APERCU = E.APERCU === "1" || E.APERCU === "true";
const MARQUEUR = path.join(RACINE, "data", "dernier_envoi_pouls.json");

const lire = (f, defaut) => { try { return JSON.parse(fs.readFileSync(path.join(RACINE, f), "utf8")); } catch (e) { return defaut; } };
const log = (...a) => console.log(...a);

// ---------- Mise en forme ----------
const fcfa = (v) => Math.round(v).toLocaleString("fr-FR").replace(/ | /g, " ");
const nb1 = (v) => v.toFixed(1).replace(".", ",");
const pct = (v, d = 2) => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(d).replace(".", ",")} %`;
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ACRONYMES = new Set(["CI", "SN", "BF", "BN", "ML", "NG", "TG", "SGBCI", "SIBC", "SMB", "BIIC", "BICI", "BOA", "SODE", "CIE", "SAFC", "ETI", "NEI", "CEDA", "SAPH", "SETAO", "SIEM", "SICOR", "II"]);
const MOTS = { "COTE": "Côte", "D'IVOIRE": "d'Ivoire", "SOCIETE": "Société", "DE": "de", "DU": "du", "BERNABE": "Bernabé", "BENIN": "Bénin" };
const joli = (n) => String(n).split(/(\s+)/).map((w) => { const u = w.toUpperCase(); const nu = u.replace(/[().,]/g, ""); if (ACRONYMES.has(nu)) return u; if (MOTS[nu]) return MOTS[nu]; return u.charAt(0) + u.slice(1).toLowerCase(); }).join("");

// ---------- Calculs (reprise exacte des formules de l'application, aux cours de clôture) ----------
const clamp = (x) => Math.max(0, Math.min(1, x));
const mediane = (arr) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const VALO_R = 0.1133, VALO_G = 0.03, VALO_GRAHAM = 22.5;

function scoreHBI(b, medPER, medPBR) {
  const rel = (x, med) => (x === null || !med ? 0 : clamp((2 - x / med) / 1.5));
  const valo = 12.5 * rel(b.per, medPER) + 12.5 * rel(b.pbr, medPBR);
  const lvl = b.dy === null ? 0 : clamp(b.dy / 0.08);
  const sus = b.dy === null || b.dy <= 0 ? 0 : (b.payout === null ? 0.5 : clamp(1 - (b.payout - 0.6) / 0.4));
  const rend = 15 * lvl + 10 * sus;
  const croiss = 10 * (b.gCA === null ? 0 : clamp(b.gCA / 0.15)) + 15 * (b.gRN === null ? 0 : clamp(b.gRN / 0.3));
  const renta = 15 * (b.roe === null ? 0 : clamp(b.roe / 0.2)) + 10 * (b.marge === null ? 0 : clamp(b.marge / 0.15));
  const t = valo + rend + croiss + renta;
  return Number.isFinite(t) ? t : 0;
}

function calculerFondamentaux(societes, prix) {
  const n = (v) => (v === null || v === undefined || !Number.isFinite(v) ? null : v);
  const base = societes.map((s) => {
    const cours = prix[s.ticker] ?? n(s.coursRef);
    const sc = s.scr || {}, vl = s.valo || {};
    const bnpa = n(sc.bnpa), vmc = n(sc.vmc), dv = n(sc.divNet);
    return {
      s, cours,
      // Note HBI
      per: cours && bnpa && bnpa > 0 ? cours / bnpa : null,
      pbr: cours && vmc && vmc > 0 ? cours / vmc : null,
      dy: cours && dv !== null && dv >= 0 ? dv / cours : null,
      payout: n(sc.payout), gRN: n(sc.gRN), gCA: n(sc.gCA), roe: n(sc.roe), marge: n(sc.marge),
      // Valeur réelle
      vb: n(vl.bnpa), vv: n(vl.bvps), vd: n(vl.dn),
    };
  });
  base.forEach((b) => { b.vper = b.cours && b.vb > 0 ? b.cours / b.vb : null; b.vpbr = b.cours && b.vv > 0 ? b.cours / b.vv : null; });
  const medPER = mediane(base.filter((b) => b.per !== null).map((b) => b.per));
  const medPBR = mediane(base.filter((b) => b.pbr !== null).map((b) => b.pbr));
  const okPer = (x) => x.vper !== null && x.vper > 0 && x.vper <= 60, okPbr = (x) => x.vpbr !== null && x.vpbr > 0 && x.vpbr <= 15;
  base.forEach((r) => {
    r.note = scoreHBI(r, medPER, medPBR);
    const pairs = base.filter((o) => o.s.name !== r.s.name && o.s.secteur === r.s.secteur);
    const secPer = pairs.filter(okPer).map((o) => o.vper), secPbr = pairs.filter(okPbr).map((o) => o.vpbr);
    const useSector = secPer.length >= 3 && secPbr.length >= 3;
    const refPer = mediane(useSector ? secPer : base.filter((o) => o.s.name !== r.s.name && okPer(o)).map((o) => o.vper));
    const refPbr = mediane(useSector ? secPbr : base.filter((o) => o.s.name !== r.s.name && okPbr(o)).map((o) => o.vpbr));
    const methodes = [];
    const cp = r.vb > 0 && refPer ? r.vb * refPer : null, cb = r.vv > 0 && refPbr ? r.vv * refPbr : null;
    const comp = [cp, cb].filter((x) => x !== null);
    if (comp.length) methodes.push(comp.reduce((a, b) => a + b, 0) / comp.length);
    if (r.vd > 0) methodes.push(r.vd * (1 + VALO_G) / (VALO_R - VALO_G));
    if (r.vb > 0 && r.vv > 0) methodes.push(Math.sqrt(VALO_GRAHAM * r.vb * r.vv));
    if (r.s.secteur === "Services financiers" && r.vb > 0 && r.vv > 0 && r.vb / r.vv > VALO_G) {
      const roe = r.vb / r.vv; methodes.push(r.vv * Math.max(0, (roe - VALO_G) / (VALO_R - VALO_G)));
    }
    r.valeur = methodes.length >= 2 ? mediane(methodes) : null;
    r.potentiel = r.valeur && r.cours ? r.valeur / r.cours - 1 : null;
  });
  return base.filter((r) => !r.s.arret);
}

// ---------- Contenu du jour ----------
function construire(coursJson, fond, jourIso) {
  const lignes = coursJson.rows || [];
  const nomDe = {}, secDe = {};
  fond.societes.forEach((s) => { if (s.ticker) { nomDe[s.ticker] = joli(s.name); secDe[s.ticker] = s.secteur; } });
  const prix = {};
  lignes.forEach((r) => { if (r.dernier) prix[r.s] = r.dernier; else if (r.veille) prix[r.s] = r.veille; });
  const mouv = lignes.filter((r) => r.dernier && r.veille).map((r) => ({ sym: r.s, nom: nomDe[r.s] || r.s, cours: r.dernier, var: r.dernier / r.veille - 1, volume: r.volume || 0 }));
  const hausses = mouv.filter((r) => r.var > 0).sort((a, b) => b.var - a.var).slice(0, 5);
  const baisses = mouv.filter((r) => r.var < 0).sort((a, b) => a.var - b.var).slice(0, 5);
  const volumes = lignes.filter((r) => r.volume > 0).map((r) => { const c = r.dernier || r.veille || 0; return { sym: r.s, nom: nomDe[r.s] || r.s, volume: r.volume, valeur: r.volume * c }; })
    .sort((a, b) => b.volume - a.volume).slice(0, 5);
  const f = calculerFondamentaux(fond.societes.filter((s) => s.ticker), prix).map((r) => ({ ...r, sym: r.s.ticker, nom: joli(r.s.name), secteur: r.s.secteur }));
  const notes = [...f].sort((a, b) => b.note - a.note).slice(0, 5);
  const rendements = f.filter((r) => r.dy !== null && r.dy > 0 && r.dy < 0.3).sort((a, b) => b.dy - a.dy).slice(0, 5);
  const sousEval = f.filter((r) => r.potentiel !== null && r.potentiel > 0).sort((a, b) => b.potentiel - a.potentiel).slice(0, 5);
  // Nouveautés publiées aujourd'hui (rapports financiers, BOC)
  const [y, m, d] = jourIso.split("-"); const jourFr = `${d}/${m}/${y}`;
  const rapports = lire("publications/index.json", []).filter((e) => e && e.date === jourFr).map((e) => ({ type: "rapport", titre: `${joli(e.societe)} — ${e.titre}` }));
  const boc = fs.existsSync(path.join(RACINE, "publications", "boc", `BOC_${y}${m}${d}.pdf`)) ? [{ type: "boc", titre: `Bulletin Officiel de la Cote du ${jourFr}` }] : [];
  return { date: jourFr, source: coursJson.source || "", hausses, baisses, volumes, notes, rendements, sousEval, nouveautes: [...boc, ...rapports] };
}

// ---------- Email HTML ----------
function htmlEmail(c) {
  const th = (t, al = "left") => `<th style="padding:6px 8px;text-align:${al};font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:${VERT};border-bottom:2px solid ${OR};background:${OR_CLAIR}">${t}</th>`;
  const td = (t, al = "left", extra = "") => `<td style="padding:7px 8px;text-align:${al};font-size:13.5px;color:#1B2A22;border-bottom:1px solid #E7E2D3;${extra}">${t}</td>`;
  const table = (titre, sous, entetes, lignes) => `
    <div style="margin:18px 0 6px;font-size:15px;font-weight:700;color:${VERT}">${titre}</div>
    ${sous ? `<div style="font-size:12px;color:#5C6B62;margin-bottom:6px">${sous}</div>` : ""}
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse"><tr>${entetes.map((h) => th(h[0], h[1])).join("")}</tr>
    ${lignes.length ? lignes.join("") : `<tr>${td("Aucune valeur aujourd'hui", "left", "color:#5C6B62")}</tr>`}</table>`;
  const nom = (r) => `<b>${esc(r.nom)}</b><br><span style="font-size:11.5px;color:#5C6B62">${esc(r.sym)}${r.secteur ? " · " + esc(r.secteur) : ""}</span>`;
  const vert = "#1E7A4C", rouge = "#B3392B";
  const lH = c.hausses.map((r) => `<tr>${td(nom(r))}${td(fcfa(r.cours) + " FCFA", "right")}${td(pct(r.var), "right", `font-weight:700;color:${vert}`)}</tr>`);
  const lB = c.baisses.map((r) => `<tr>${td(nom(r))}${td(fcfa(r.cours) + " FCFA", "right")}${td(pct(r.var), "right", `font-weight:700;color:${rouge}`)}</tr>`);
  const lV = c.volumes.map((r) => `<tr>${td(nom(r))}${td(fcfa(r.volume) + " titres", "right")}${td(fcfa(r.valeur) + " FCFA", "right")}</tr>`);
  const lN = c.notes.map((r, i) => `<tr>${td(`${i + 1}`, "center", "font-weight:700")}${td(nom(r))}${td(fcfa(r.cours) + " FCFA", "right")}${td(`${nb1(r.note)} / 100`, "right", `font-weight:700;color:${VERT}`)}</tr>`);
  const lR = c.rendements.map((r, i) => `<tr>${td(`${i + 1}`, "center", "font-weight:700")}${td(nom(r))}${td(fcfa(r.cours) + " FCFA", "right")}${td(nb1(r.dy * 100) + " %", "right", `font-weight:700;color:${VERT}`)}</tr>`);
  const lS = c.sousEval.map((r, i) => `<tr>${td(`${i + 1}`, "center", "font-weight:700")}${td(nom(r))}${td(fcfa(r.cours) + " FCFA", "right")}${td(fcfa(r.valeur) + " FCFA", "right")}${td("+" + nb1(r.potentiel * 100) + " %", "right", `font-weight:700;color:${VERT}`)}</tr>`);
  const nouv = c.nouveautes.length ? `
    <div style="margin:18px 0 0;border:1px solid ${OR};border-left:5px solid ${OR};background:${OR_CLAIR};border-radius:6px;padding:10px 14px">
      <div style="font-size:13px;font-weight:700;color:${VERT}">📄 Nouveauté publiée aujourd'hui</div>
      ${c.nouveautes.map((x) => `<div style="font-size:13.5px;color:#1B2A22;margin-top:4px">• ${esc(x.titre)}</div>`).join("")}
    </div>` : "";
  const bloc = (num, titre, sous) => `<div style="background:${VERT};color:${BLANC};padding:10px 16px;border-radius:6px;margin-top:22px"><div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#E3C57F">Bloc ${num}</div><div style="font-size:16px;font-weight:700">${titre}</div>${sous ? `<div style="font-size:12px;opacity:.9;margin-top:2px">${sous}</div>` : ""}</div>`;
  return `<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pouls du Marché BRVM — ${c.date}</title></head>
<body style="margin:0;padding:0;background:#EEF1F0;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:14px 8px">
<table role="presentation" width="640" cellspacing="0" cellpadding="0" style="max-width:640px;width:100%;background:${BLANC};border-radius:10px;overflow:hidden">
<tr><td style="background:${VERT};padding:20px 22px;border-bottom:4px solid ${OR}">
  <img src="${APP_URL}icon-192.png" width="56" height="56" alt="HBI" style="vertical-align:middle;border-radius:10px;background:#fff;margin-right:12px">
  <span style="vertical-align:middle;display:inline-block"><span style="display:block;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#E3C57F">Bilan quotidien · 15h15</span>
  <span style="display:block;font-size:22px;font-weight:700;color:#fff">Pouls du Marché BRVM</span>
  <span style="display:block;font-size:13px;color:#E3C57F">Séance du ${c.date}${c.source ? " · " + esc(c.source) : ""}</span></span>
</td></tr>
<tr><td style="padding:6px 22px 22px">
  ${bloc(1, "Le bilan de la séance du jour", "Mouvements aux cours de clôture")}
  ${table("▲ Les 5 plus fortes hausses", "", [["Société"], ["Clôture", "right"], ["Variation", "right"]], lH)}
  ${table("▼ Les 5 plus fortes baisses", "", [["Société"], ["Clôture", "right"], ["Variation", "right"]], lB)}
  ${table("📊 Les 5 plus gros volumes échangés", "La valeur est estimée : quantité × cours de clôture.", [["Société"], ["Quantité", "right"], ["Valeur", "right"]], lV)}
  ${bloc(2, "Le pouls fondamental & classements HBI du jour", "Recalculés aux cours de clôture")}
  ${table("🏅 Les 5 meilleures notes globales HBI", "Prix, dividende, croissance et rentabilité réunis (sur 100).", [["#", "center"], ["Société"], ["Cours", "right"], ["Note", "right"]], lN)}
  ${table("💰 Les 5 meilleurs rendements nets de dividende", "Dividende net du dernier exercice ÷ cours du jour.", [["#", "center"], ["Société"], ["Cours", "right"], ["Rendement", "right"]], lR)}
  ${table("🏷️ Les 5 actions les plus sous-évaluées", "Plus fort potentiel entre le cours du jour et la valeur réelle estimée HBI.", [["#", "center"], ["Société"], ["Cours", "right"], ["Valeur réelle", "right"], ["Potentiel", "right"]], lS)}
  ${nouv}
  <div style="text-align:center;margin:26px 0 8px"><a href="${APP_URL}?p=actualites" style="display:inline-block;background:${OR};color:#fff;text-decoration:none;font-weight:700;font-size:15px;padding:13px 26px;border-radius:8px">Ouvrir l'application Horizon Bourse Invest</a></div>
  <div style="font-size:11px;color:#5C6B62;line-height:1.5;text-align:center;margin-top:14px">Information pédagogique fondée sur les cours officiels de la BRVM et sur les comptes publiés ; ce n'est pas un conseil en investissement. Les performances passées ne préjugent pas des performances futures.</div>
</td></tr>
<tr><td style="background:${VERT};padding:16px 22px;text-align:center">
  <div style="font-size:14px;font-weight:700;color:#E3C57F;letter-spacing:1px">Discipline • Rigueur • Patience</div>
  <div style="font-size:11px;color:#C9D6CE;margin-top:8px"><a href="{{ unsubscribe }}" style="color:#C9D6CE">Se désabonner</a></div>
</td></tr>
</table></td></tr></table></body></html>`;
}

function texteNotif(c) {
  const h = c.hausses[0], v = c.volumes[0], n = c.notes[0];
  const parts = [];
  if (h) parts.push(`Top hausse ${h.nom} ${pct(h.var, 1)}`);
  if (v) parts.push(`Top volume ${v.nom}`);
  if (n) parts.push(`N°1 Note HBI : ${n.nom} ${Math.round(n.note)}/100`);
  return { titre: `Clôture BRVM du ${c.date}`, corps: `${parts.join(" • ")}. Découvrez le bilan complet !` };
}

// ---------- Envoi ----------
async function api(url, options) {
  const r = await fetch(url, options); const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch (e) { /* texte */ }
  if (!r.ok) throw new Error(`${r.status} ${t.slice(0, 300)}`);
  return j;
}
async function envoyerEmail(c, html) {
  const cle = E.BREVO_API_KEY, liste = parseInt(E.BREVO_LIST_ID, 10);
  if (!cle || !liste) throw new Error("BREVO_API_KEY / BREVO_LIST_ID manquants");
  const H = { "api-key": cle, "content-type": "application/json", accept: "application/json" };
  let expediteur = E.BREVO_SENDER_EMAIL ? { name: "Horizon Bourse Invest", email: E.BREVO_SENDER_EMAIL } : null;
  if (!expediteur) {
    const s = await api("https://api.brevo.com/v3/senders", { headers: H });
    const ok = (s.senders || []).find((x) => x.active) || (s.senders || [])[0];
    if (!ok) throw new Error("Aucun expéditeur validé dans Brevo (menu Expéditeurs, domaines et IP)");
    expediteur = { name: "Horizon Bourse Invest", email: ok.email };
  }
  const camp = await api("https://api.brevo.com/v3/emailCampaigns", { method: "POST", headers: H, body: JSON.stringify({
    name: `Pouls du marché ${c.date} (${new Date().toISOString().slice(11, 16)} UTC)`, subject: `Pouls du Marché BRVM — séance du ${c.date}`,
    sender: expediteur, htmlContent: html, recipients: { listIds: [liste] },
  }) });
  await api(`https://api.brevo.com/v3/emailCampaigns/${camp.id}/sendNow`, { method: "POST", headers: H });
  return camp.id;
}
async function envoyerPush(c) {
  const id = E.ONESIGNAL_APP_ID, cle = E.ONESIGNAL_REST_API_KEY;
  if (!id || !cle) throw new Error("ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY manquants");
  const t = texteNotif(c);
  const j = await api("https://api.onesignal.com/notifications", { method: "POST", headers: { "content-type": "application/json", authorization: `Key ${cle}` }, body: JSON.stringify({
    app_id: id, target_channel: "push", included_segments: ["Total Subscribers"],
    headings: { fr: t.titre, en: t.titre }, contents: { fr: t.corps, en: t.corps }, url: `${APP_URL}?p=actualites`,
    chrome_web_icon: `${APP_URL}icon-192.png`, firefox_icon: `${APP_URL}icon-192.png`,
  }) });
  return j && j.id;
}

(async () => {
  // Configuration publique lue par l'application (l'identifiant OneSignal n'est pas secret).
  try {
    const cfg = { onesignal_app_id: E.ONESIGNAL_APP_ID || "", brevo_form_url: E.BREVO_FORM_URL || "" };
    const fichier = path.join(RACINE, "config-push.json"); const ancien = fs.existsSync(fichier) ? fs.readFileSync(fichier, "utf8") : "";
    const neuf = JSON.stringify(cfg, null, 1) + "\n"; if (neuf !== ancien && (cfg.onesignal_app_id || cfg.brevo_form_url || ancien)) fs.writeFileSync(fichier, neuf);
  } catch (e) { log("config-push.json non écrit :", e.message); }

  const coursJson = lire("cours.json", null);
  if (!coursJson || !coursJson.date) { log("STOP : cours.json illisible."); return; }
  const auj = new Date().toISOString().slice(0, 10); const [y, m, d] = auj.split("-"); const aujFr = `${d}/${m}/${y}`;

  // 1) Fraîcheur : les cours enregistrés doivent être ceux du jour (sinon : férié BRVM ou mise à jour pas encore faite).
  if (!FORCER && coursJson.date !== aujFr) { log(`STOP (fraîcheur) : cours du ${coursJson.date}, aujourd'hui ${aujFr} — jour férié ou mise à jour absente. Rien envoyé.`); return; }
  if (!FORCER && coursJson.provisoire) { log("STOP (fraîcheur) : les cours du jour sont encore provisoires (clôture non officialisée). Rien envoyé."); return; }
  // 2) Anti-doublon : un seul envoi validé par date et par canal.
  const marq = lire("data/dernier_envoi_pouls.json", {});
  const deja = marq.date === coursJson.date ? marq : { date: coursJson.date, email: false, push: false };
  if (!FORCER && deja.email && deja.push) { log(`STOP (doublon) : l'envoi du ${coursJson.date} est déjà validé.`); return; }

  const fond = lire("data/fondamentaux.json", null);
  if (!fond || !Array.isArray(fond.societes)) { log("STOP : data/fondamentaux.json manquant."); process.exitCode = 1; return; }
  const iso = `${coursJson.date.slice(6)}-${coursJson.date.slice(3, 5)}-${coursJson.date.slice(0, 2)}`;
  const contenu = construire(coursJson, fond, iso);
  const html = htmlEmail(contenu), notif = texteNotif(contenu);
  log(`Séance du ${contenu.date} : ${contenu.hausses.length} hausses, ${contenu.baisses.length} baisses, ${contenu.volumes.length} volumes ; N°1 note : ${contenu.notes[0] ? contenu.notes[0].nom : "—"}.`);
  log("Notification :", notif.titre, "|", notif.corps);
  if (APERCU) { fs.writeFileSync(path.join(RACINE, "apercu-pouls.html"), html); log("Aperçu écrit : apercu-pouls.html (rien envoyé)."); return; }

  let ok = false;
  if (!deja.email) {
    if (E.BREVO_API_KEY && E.BREVO_LIST_ID) { try { const id = await envoyerEmail(contenu, html); deja.email = true; ok = true; log("Email envoyé (campagne Brevo " + id + ")."); } catch (e) { log("ÉCHEC email :", e.message); process.exitCode = 1; } }
    else log("Email ignoré : secrets Brevo non configurés.");
  }
  if (!deja.push) {
    if (E.ONESIGNAL_APP_ID && E.ONESIGNAL_REST_API_KEY) { try { const id = await envoyerPush(contenu); deja.push = true; ok = true; log("Notification push envoyée (" + id + ")."); } catch (e) { log("ÉCHEC push :", e.message); process.exitCode = 1; } }
    else log("Push ignoré : secrets OneSignal non configurés.");
  }
  if (ok && !FORCER) { fs.mkdirSync(path.dirname(MARQUEUR), { recursive: true }); fs.writeFileSync(MARQUEUR, JSON.stringify({ date: deja.date, email: deja.email, push: deja.push, envoye_le: new Date().toISOString() }, null, 1) + "\n"); }
})();
