import React, { useState, useContext, createContext, useRef } from "react";
import {
  Plus, FileText, BarChart3, Inbox, Settings, LayoutDashboard, Calendar, Clock,
  MapPin, User, Users, Tag, Image as ImageIcon, ChevronRight, ChevronLeft, GripVertical,
  Trash2, Copy, Eye, Sun, Moon, Search, Filter, Download, Printer, QrCode, Share2,
  Sparkles, Check, X, ArrowLeft, ArrowRight, Mail, Phone, MessageCircle, Home, Globe,
  Briefcase, Landmark, Award, BadgeCheck, ListChecks, CheckSquare, ChevronDown, Type,
  Paperclip, PenTool, Send, Bell, Palette, Upload, ScanLine, UserCheck, UserX, Menu,
  Settings2, Link2, FileSpreadsheet, FileDown, Star, Wand2, ChevronUp
} from "lucide-react";

/* ---------------------------------------------------------------------- */
/* Tokens & data                                                          */
/* ---------------------------------------------------------------------- */

const ACCENT = "#2A3F8F";       // bleu royal
const ACCENT_DEEP = "#182A66";  // bleu royal profond
const GOLD = "#C9A24B";
const GOLD_LIGHT = "#E8C874";

const ThemeCtx = createContext(null);
const useT = () => useContext(ThemeCtx);

const FIELD_LIBRARY = {
  "Informations personnelles": [
    { type: "fullname", label: "Nom complet", icon: User },
    { type: "photo", label: "Photo", icon: ImageIcon },
    { type: "gender", label: "Sexe", icon: Users },
    { type: "birthdate", label: "Date de naissance", icon: Calendar },
    { type: "email", label: "Email", icon: Mail },
    { type: "phone", label: "Téléphone", icon: Phone },
    { type: "whatsapp", label: "WhatsApp", icon: MessageCircle },
    { type: "address", label: "Adresse", icon: Home },
    { type: "country", label: "Pays", icon: Globe },
    { type: "city", label: "Ville", icon: MapPin },
    { type: "profession", label: "Profession", icon: Briefcase },
    { type: "church", label: "Église", icon: Landmark },
    { type: "ministry", label: "Ministère", icon: Award },
    { type: "role", label: "Fonction", icon: BadgeCheck },
  ],
  "Champs avancés": [
    { type: "mcq", label: "Choix multiple", icon: ListChecks },
    { type: "checkbox", label: "Cases à cocher", icon: CheckSquare },
    { type: "dropdown", label: "Liste déroulante", icon: ChevronDown },
    { type: "textarea", label: "Zone de texte", icon: Type },
    { type: "upload", label: "Téléchargement de document", icon: Paperclip },
    { type: "signature", label: "Signature électronique", icon: PenTool },
    { type: "custom", label: "Champ personnalisé", icon: Sparkles },
  ],
};

const ALL_FIELDS = Object.values(FIELD_LIBRARY).flat();

const DEFAULT_FIELDS = [
  { id: "f1", type: "fullname", label: "Nom complet", required: true },
  { id: "f2", type: "email", label: "Email", required: true },
  { id: "f3", type: "whatsapp", label: "WhatsApp", required: false },
  { id: "f4", type: "church", label: "Église", required: false },
];

const SAMPLE_FORMS = [
  { id: 1, name: "Convention Jeunesse 2026", status: "Publié", responses: 342, max: 500, date: "12 sept. 2026", color: ACCENT },
  { id: 2, name: "Retraite des Femmes — Vision", status: "Publié", responses: 128, max: 150, date: "3 oct. 2026", color: GOLD },
  { id: 3, name: "École du Dimanche — Rentrée", status: "Brouillon", responses: 0, max: 200, date: "—", color: "#6B7280" },
  { id: 4, name: "Séminaire des Ministères", status: "Clôturé", responses: 210, max: 210, date: "18 juil. 2026", color: "#6B7280" },
];

const SAMPLE_RESPONSES = [
  { id: "REG-0931", name: "Naomi Kalonji", email: "naomi.k@email.com", phone: "+243 991 234 567", date: "28 juil. 2026", status: "Présent" },
  { id: "REG-0932", name: "Josué Mbala", email: "josue.m@email.com", phone: "+243 990 112 233", date: "28 juil. 2026", status: "En attente" },
  { id: "REG-0933", name: "Grace Tshibangu", email: "grace.t@email.com", phone: "+243 981 556 789", date: "29 juil. 2026", status: "Absent" },
  { id: "REG-0934", name: "Emmanuel Ilunga", email: "emmanuel.i@email.com", phone: "+243 970 442 991", date: "29 juil. 2026", status: "Présent" },
  { id: "REG-0935", name: "Ruth Kabeya", email: "ruth.k@email.com", phone: "+243 995 667 001", date: "30 juil. 2026", status: "Présent" },
];

/* ---------------------------------------------------------------------- */
/* Small primitives                                                       */
/* ---------------------------------------------------------------------- */

function Card({ children, className = "", onClick, style }) {
  const t = useT();
  return (
    <div
      onClick={onClick}
      style={style}
      className={`rounded-2xl border ${t.card} ${className}`}
    >
      {children}
    </div>
  );
}

function PrimaryButton({ children, onClick, icon: Icon, className = "", type = "button", full }) {
  return (
    <button
      type={type}
      onClick={onClick}
      className={`inline-flex ${full ? "w-full" : ""} items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-transform active:scale-[0.98] hover:brightness-110 ${className}`}
      style={{ background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DEEP} 100%)` }}
    >
      {Icon && <Icon size={16} />}
      {children}
    </button>
  );
}

function GhostButton({ children, onClick, icon: Icon, className = "", full }) {
  const t = useT();
  return (
    <button
      onClick={onClick}
      className={`inline-flex ${full ? "w-full" : ""} items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold border ${t.border} ${t.hover} ${t.text} transition ${className}`}
    >
      {Icon && <Icon size={16} />}
      {children}
    </button>
  );
}

function Toggle({ checked, onChange, label, sub }) {
  const t = useT();
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div>
        <p className={`text-sm font-medium ${t.text}`}>{label}</p>
        {sub && <p className={`text-xs ${t.subtext} mt-0.5`}>{sub}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className="relative h-6 w-11 shrink-0 rounded-full transition-colors"
        style={{ background: checked ? ACCENT : t.dark ? "#333747" : "#E2E4EA" }}
      >
        <span
          className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
          style={{ transform: checked ? "translateX(22px)" : "translateX(2px)" }}
        />
      </button>
    </div>
  );
}

function Field({ label, children, hint }) {
  const t = useT();
  return (
    <label className="block">
      <span className={`text-xs font-semibold uppercase tracking-wide ${t.subtext}`}>{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <span className={`text-xs ${t.subtext}`}>{hint}</span>}
    </label>
  );
}

function inputCls(t) {
  return `w-full rounded-xl border ${t.border} ${t.inputBg} ${t.text} px-3.5 py-2.5 text-sm outline-none focus:ring-2 transition placeholder:${t.subtextClass || ""}`;
}

function Pill({ children, tone = "neutral" }) {
  const tones = {
    neutral: "bg-gray-100 text-gray-600",
    gold: "text-white",
    blue: "text-white",
    ok: "bg-emerald-100 text-emerald-700",
    warn: "bg-amber-100 text-amber-700",
    off: "bg-gray-100 text-gray-500",
  };
  const style = tone === "gold" ? { background: GOLD } : tone === "blue" ? { background: ACCENT } : {};
  return (
    <span style={style} className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone] || tones.neutral}`}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------------- */
/* Sidebar & Topbar                                                       */
/* ---------------------------------------------------------------------- */

function Sidebar({ screen, setScreen, mobileOpen, setMobileOpen }) {
  const t = useT();
  const items = [
    { id: "dashboard", label: "Tableau de bord", icon: LayoutDashboard },
    { id: "myforms", label: "Mes formulaires", icon: FileText },
    { id: "stats", label: "Statistiques", icon: BarChart3 },
    { id: "responses", label: "Réponses reçues", icon: Inbox },
    { id: "settings", label: "Paramètres", icon: Settings },
  ];
  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setMobileOpen(false)} />
      )}
      <aside
        className={`fixed z-40 inset-y-0 left-0 w-64 border-r ${t.sidebar} flex flex-col transition-transform lg:translate-x-0 lg:static lg:z-0
        ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div
            className="h-9 w-9 rounded-xl flex items-center justify-center text-white font-display font-semibold text-sm"
            style={{ background: `linear-gradient(135deg, ${GOLD_LIGHT}, ${GOLD})` }}
          >
            G2
          </div>
          <div>
            <p className={`font-display font-semibold leading-tight ${t.text}`}>Glory2YahPub</p>
            <p className={`text-[11px] ${t.subtext} leading-tight`}>Forms</p>
          </div>
        </div>

        <nav className="flex-1 px-3 space-y-1 mt-2">
          {items.map((it) => {
            const active = screen === it.id;
            return (
              <button
                key={it.id}
                onClick={() => { setScreen(it.id); setMobileOpen(false); }}
                className={`w-full flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                  active ? "text-white" : `${t.text} ${t.hover}`
                }`}
                style={active ? { background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_DEEP})` } : {}}
              >
                <it.icon size={17} />
                {it.label}
              </button>
            );
          })}
        </nav>

        <div className="p-3">
          <button
            onClick={() => { setScreen("builder-1"); setMobileOpen(false); }}
            className="w-full flex items-center justify-center gap-2 rounded-xl px-3.5 py-2.5 text-sm font-semibold text-white shadow-sm"
            style={{ background: `linear-gradient(135deg, ${GOLD_LIGHT}, ${GOLD})` }}
          >
            <Plus size={16} /> Nouveau formulaire
          </button>
        </div>
      </aside>
    </>
  );
}

function Topbar({ title, subtitle, setMobileOpen }) {
  const t = useT();
  return (
    <header className={`sticky top-0 z-20 flex items-center justify-between gap-3 border-b ${t.border} ${t.bg} px-4 sm:px-6 py-4 backdrop-blur`}>
      <div className="flex items-center gap-3 min-w-0">
        <button onClick={() => setMobileOpen(true)} className={`lg:hidden rounded-lg p-2 ${t.hover}`}>
          <Menu size={20} className={t.text} />
        </button>
        <div className="min-w-0">
          <h1 className={`font-display text-lg sm:text-xl font-semibold truncate ${t.text}`}>{title}</h1>
          {subtitle && <p className={`text-xs sm:text-sm ${t.subtext} truncate`}>{subtitle}</p>}
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <ThemeSwitch />
        <div
          className="h-9 w-9 rounded-full flex items-center justify-center text-white text-xs font-semibold"
          style={{ background: `linear-gradient(135deg, ${ACCENT}, ${GOLD})` }}
        >
          PM
        </div>
      </div>
    </header>
  );
}

function ThemeSwitch() {
  const t = useT();
  return (
    <button
      onClick={t.toggle}
      className={`rounded-full p-2 border ${t.border} ${t.hover}`}
      aria-label="Basculer le mode sombre"
    >
      {t.dark ? <Sun size={16} className="text-amber-300" /> : <Moon size={16} className={t.text} />}
    </button>
  );
}

/* ---------------------------------------------------------------------- */
/* Dashboard                                                              */
/* ---------------------------------------------------------------------- */

function Dashboard({ setScreen }) {
  const t = useT();
  const actions = [
    { id: "builder-1", label: "Créer un formulaire", icon: Plus, desc: "Nouvel événement en 4 étapes" },
    { id: "myforms", label: "Mes formulaires", icon: FileText, desc: "Gérer et éditer vos formulaires" },
    { id: "stats", label: "Statistiques", icon: BarChart3, desc: "Suivre les inscriptions en direct" },
    { id: "responses", label: "Réponses reçues", icon: Inbox, desc: "Consulter et exporter les inscrits" },
    { id: "settings", label: "Paramètres", icon: Settings, desc: "Marque, notifications, intégrations" },
  ];

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Hero */}
      <Card className="relative overflow-hidden p-6 sm:p-8">
        <div
          className="pointer-events-none absolute -top-16 -right-16 h-56 w-56 rounded-full opacity-30 blur-3xl"
          style={{ background: `radial-gradient(circle, ${GOLD} 0%, transparent 70%)` }}
        />
        <div
          className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full opacity-20 blur-3xl"
          style={{ background: `radial-gradient(circle, ${ACCENT} 0%, transparent 70%)` }}
        />
        <p className={`text-xs font-semibold uppercase tracking-widest`} style={{ color: GOLD }}>Bienvenue</p>
        <h2 className={`font-display text-2xl sm:text-3xl font-semibold mt-1 ${t.text}`}>
          Créez un formulaire d'inscription en quelques minutes
        </h2>
        <p className={`mt-2 max-w-xl text-sm ${t.subtext}`}>
          Glissez-déposez vos champs, personnalisez le style, publiez et suivez vos inscrits — tout est synchronisé avec votre communauté Glory2YahPub.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <PrimaryButton icon={Plus} onClick={() => setScreen("builder-1")}>Créer un nouveau formulaire</PrimaryButton>
          <GhostButton icon={Wand2} onClick={() => setScreen("builder-2")}>Générer avec l'assistant IA</GhostButton>
        </div>
      </Card>

      {/* Quick actions */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {actions.map((a) => (
          <Card key={a.id} onClick={() => setScreen(a.id)} className={`p-4 cursor-pointer ${t.hover} transition`}>
            <div
              className="h-10 w-10 rounded-xl flex items-center justify-center mb-3"
              style={{ background: `${ACCENT}1A` }}
            >
              <a.icon size={18} style={{ color: ACCENT }} />
            </div>
            <p className={`text-sm font-semibold ${t.text}`}>{a.label}</p>
            <p className={`text-xs ${t.subtext} mt-0.5 hidden sm:block`}>{a.desc}</p>
          </Card>
        ))}
      </div>

      {/* Recent forms */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className={`font-display text-lg font-semibold ${t.text}`}>Formulaires récents</h3>
          <button onClick={() => setScreen("myforms")} className="text-sm font-semibold flex items-center gap-1" style={{ color: ACCENT }}>
            Tout voir <ChevronRight size={15} />
          </button>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          {SAMPLE_FORMS.map((f) => (
            <Card key={f.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className={`text-sm font-semibold truncate ${t.text}`}>{f.name}</p>
                  <p className={`text-xs ${t.subtext} mt-0.5`}>{f.date}</p>
                </div>
                <Pill tone={f.status === "Publié" ? "ok" : f.status === "Brouillon" ? "warn" : "off"}>{f.status}</Pill>
              </div>
              <div className="mt-3">
                <div className={`h-1.5 w-full rounded-full ${t.dark ? "bg-white/10" : "bg-gray-100"}`}>
                  <div className="h-1.5 rounded-full" style={{ width: `${Math.min(100, (f.responses / f.max) * 100)}%`, background: f.color }} />
                </div>
                <p className={`text-xs ${t.subtext} mt-1.5`}>{f.responses} / {f.max} inscrits</p>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Mes formulaires                                                        */
/* ---------------------------------------------------------------------- */

function MyForms({ setScreen }) {
  const t = useT();
  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className={`flex items-center gap-2 rounded-xl border ${t.border} ${t.inputBg} px-3 py-2 w-full sm:w-72`}>
          <Search size={16} className={t.subtext} />
          <input placeholder="Rechercher un formulaire…" className={`bg-transparent outline-none text-sm w-full ${t.text}`} />
        </div>
        <PrimaryButton icon={Plus} onClick={() => setScreen("builder-1")}>Nouveau formulaire</PrimaryButton>
      </div>

      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {SAMPLE_FORMS.map((f) => (
          <Card key={f.id} className="p-5 flex flex-col">
            <div className="flex items-start justify-between">
              <div className="h-10 w-10 rounded-xl" style={{ background: `linear-gradient(135deg, ${f.color}, ${f.color}99)` }} />
              <Pill tone={f.status === "Publié" ? "ok" : f.status === "Brouillon" ? "warn" : "off"}>{f.status}</Pill>
            </div>
            <p className={`font-display font-semibold mt-3 ${t.text}`}>{f.name}</p>
            <p className={`text-xs ${t.subtext} mt-1`}>{f.date} · {f.responses} inscrits</p>
            <div className="mt-4 flex gap-2">
              <GhostButton className="flex-1" icon={Eye} onClick={() => setScreen("builder-4")}>Ouvrir</GhostButton>
              <GhostButton icon={Copy} />
              <GhostButton icon={Trash2} />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Builder: stepper shell                                                 */
/* ---------------------------------------------------------------------- */

const STEPS = [
  { id: 1, label: "Informations" },
  { id: 2, label: "Constructeur" },
  { id: 3, label: "Paramètres avancés" },
  { id: 4, label: "Partage" },
];

function Stepper({ step, goTo }) {
  const t = useT();
  return (
    <div className="flex items-center gap-1 sm:gap-2 overflow-x-auto pb-1">
      {STEPS.map((s, i) => (
        <React.Fragment key={s.id}>
          <button
            onClick={() => goTo(s.id)}
            className="flex items-center gap-2 shrink-0 rounded-full px-3 py-1.5"
          >
            <span
              className="h-6 w-6 rounded-full flex items-center justify-center text-xs font-semibold"
              style={{
                background: step >= s.id ? `linear-gradient(135deg, ${ACCENT}, ${ACCENT_DEEP})` : t.dark ? "#2A2E3D" : "#EEF0F4",
                color: step >= s.id ? "#fff" : t.dark ? "#9CA3AF" : "#6B7280",
              }}
            >
              {step > s.id ? <Check size={13} /> : s.id}
            </span>
            <span className={`text-xs sm:text-sm font-medium whitespace-nowrap ${step === s.id ? t.text : t.subtext}`}>{s.label}</span>
          </button>
          {i < STEPS.length - 1 && <div className={`h-px w-4 sm:w-8 ${t.dark ? "bg-white/10" : "bg-gray-200"}`} />}
        </React.Fragment>
      ))}
    </div>
  );
}

function Builder({ screen, setScreen, form, setForm, fields, setFields }) {
  const step = parseInt(screen.split("-")[1], 10);
  const t = useT();
  const [aiOpen, setAiOpen] = useState(false);

  const goTo = (n) => setScreen(`builder-${n}`);
  const next = () => goTo(Math.min(4, step + 1));
  const prev = () => (step === 1 ? setScreen("dashboard") : goTo(step - 1));

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <Stepper step={step} goTo={goTo} />
        <div className="flex items-center gap-2">
          <span className={`text-xs ${t.subtext} hidden sm:flex items-center gap-1`}><Check size={12} /> Sauvegarde automatique</span>
          <GhostButton icon={Wand2} onClick={() => setAiOpen(true)}>Assistant IA</GhostButton>
        </div>
      </div>

      {step === 1 && <StepInfo form={form} setForm={setForm} />}
      {step === 2 && <StepBuilder fields={fields} setFields={setFields} />}
      {step === 3 && <StepAdvanced form={form} setForm={setForm} />}
      {step === 4 && <StepShare form={form} />}

      <div className="flex items-center justify-between pt-2">
        <GhostButton icon={ArrowLeft} onClick={prev}>{step === 1 ? "Annuler" : "Précédent"}</GhostButton>
        {step < 4 ? (
          <PrimaryButton icon={ArrowRight} onClick={next}>Continuer</PrimaryButton>
        ) : (
          <PrimaryButton icon={Check} onClick={() => setScreen("myforms")}>Publier le formulaire</PrimaryButton>
        )}
      </div>

      {aiOpen && <AIPanel onClose={() => setAiOpen(false)} setFields={setFields} setForm={setForm} />}
    </div>
  );
}

/* ---- Step 1: infos générales ---- */

function StepInfo({ form, setForm }) {
  const t = useT();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="grid lg:grid-cols-3 gap-5">
      <Card className="lg:col-span-2 p-5 sm:p-6 space-y-4">
        <Field label="Nom de l'événement">
          <input className={inputCls(t)} placeholder="Convention Jeunesse 2026" value={form.name} onChange={set("name")} />
        </Field>
        <Field label="Description">
          <textarea rows={3} className={inputCls(t)} placeholder="Décrivez l'événement, son objectif et son public…" value={form.description} onChange={set("description")} />
        </Field>
        <Field label="Bannière de l'événement">
          <div className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed ${t.border} py-8 ${t.hover} cursor-pointer`}>
            <Upload size={20} className={t.subtext} />
            <p className={`text-xs ${t.subtext}`}>Glissez une image ici ou cliquez pour importer</p>
          </div>
        </Field>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Date"><input type="date" className={inputCls(t)} value={form.date} onChange={set("date")} /></Field>
          <Field label="Heure"><input type="time" className={inputCls(t)} value={form.time} onChange={set("time")} /></Field>
        </div>
        <Field label="Lieu">
          <div className="relative">
            <MapPin size={15} className={`absolute left-3 top-1/2 -translate-y-1/2 ${t.subtext}`} />
            <input className={inputCls(t) + " pl-9"} placeholder="Centre Glory2YahPub, Kinshasa" value={form.location} onChange={set("location")} />
          </div>
        </Field>
      </Card>

      <Card className="p-5 sm:p-6 space-y-4 h-fit">
        <Field label="Organisateur">
          <input className={inputCls(t)} placeholder="Ministère Jeunesse" value={form.organizer} onChange={set("organizer")} />
        </Field>
        <Field label="Catégorie">
          <select className={inputCls(t)} value={form.category} onChange={set("category")}>
            <option>Convention</option>
            <option>Culte</option>
            <option>Séminaire</option>
            <option>Retraite</option>
            <option>École du dimanche</option>
            <option>Autre</option>
          </select>
        </Field>
        <Field label="Nombre maximum de participants">
          <input type="number" className={inputCls(t)} placeholder="500" value={form.max} onChange={set("max")} />
        </Field>
        <Field label="Date limite d'inscription">
          <input type="date" className={inputCls(t)} value={form.deadline} onChange={set("deadline")} />
        </Field>
      </Card>
    </div>
  );
}

/* ---- Step 2: constructeur drag & drop ---- */

function StepBuilder({ fields, setFields }) {
  const t = useT();
  const [selectedId, setSelectedId] = useState(null);
  const dragIndex = useRef(null);
  const [dragOverPalette, setDragOverPalette] = useState(false);

  const addField = (lib) => {
    const id = `f${Date.now()}`;
    setFields([...fields, { id, type: lib.type, label: lib.label, required: false }]);
  };

  const removeField = (id) => {
    setFields(fields.filter((f) => f.id !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const move = (from, to) => {
    if (to < 0 || to >= fields.length) return;
    const copy = [...fields];
    const [item] = copy.splice(from, 1);
    copy.splice(to, 0, item);
    setFields(copy);
  };

  const onCanvasDrop = (e) => {
    e.preventDefault();
    setDragOverPalette(false);
    const type = e.dataTransfer.getData("fieldType");
    const lib = ALL_FIELDS.find((f) => f.type === type);
    if (lib) addField(lib);
  };

  const selected = fields.find((f) => f.id === selectedId);

  return (
    <div className="grid lg:grid-cols-[220px_1fr_260px] gap-4">
      {/* Palette */}
      <Card className="p-4 h-fit lg:sticky lg:top-20 space-y-5">
        {Object.entries(FIELD_LIBRARY).map(([cat, list]) => (
          <div key={cat}>
            <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} mb-2`}>{cat}</p>
            <div className="space-y-1.5">
              {list.map((lib) => (
                <div
                  key={lib.type}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("fieldType", lib.type)}
                  onClick={() => addField(lib)}
                  className={`flex items-center gap-2 rounded-lg border ${t.border} ${t.hover} px-2.5 py-2 text-xs cursor-grab active:cursor-grabbing ${t.text}`}
                >
                  <lib.icon size={14} style={{ color: ACCENT }} />
                  <span className="truncate">{lib.label}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Card>

      {/* Canvas */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOverPalette(true); }}
        onDragLeave={() => setDragOverPalette(false)}
        onDrop={onCanvasDrop}
        className={`rounded-2xl border-2 border-dashed ${dragOverPalette ? "border-[--gold]" : t.border} p-4 min-h-[420px] space-y-2.5 transition-colors`}
        style={dragOverPalette ? { borderColor: GOLD } : {}}
      >
        {fields.length === 0 && (
          <div className={`h-full flex flex-col items-center justify-center py-16 text-center ${t.subtext}`}>
            <Sparkles size={22} className="mb-2" />
            <p className="text-sm">Glissez un champ ici, ou cliquez dans la bibliothèque à gauche</p>
          </div>
        )}
        {fields.map((f, i) => {
          const lib = ALL_FIELDS.find((l) => l.type === f.type) || {};
          const Icon = lib.icon || Type;
          const active = selectedId === f.id;
          return (
            <div
              key={f.id}
              draggable
              onDragStart={() => (dragIndex.current = i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); if (dragIndex.current !== null) move(dragIndex.current, i); }}
              onClick={() => setSelectedId(f.id)}
              className={`flex items-center gap-3 rounded-xl border px-3 py-3 cursor-pointer ${t.card} ${active ? "" : t.border}`}
              style={active ? { borderColor: ACCENT, boxShadow: `0 0 0 2px ${ACCENT}33` } : {}}
            >
              <GripVertical size={15} className={t.subtext} />
              <div className="h-8 w-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${ACCENT}1A` }}>
                <Icon size={15} style={{ color: ACCENT }} />
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-medium truncate ${t.text}`}>{f.label}</p>
                <p className={`text-[11px] ${t.subtext}`}>{f.required ? "Obligatoire" : "Optionnel"}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={(e) => { e.stopPropagation(); move(i, i - 1); }} className={`rounded-md p-1 ${t.hover}`}><ChevronUp size={14} className={t.subtext} /></button>
                <button onClick={(e) => { e.stopPropagation(); move(i, i + 1); }} className={`rounded-md p-1 ${t.hover}`}><ChevronDown size={14} className={t.subtext} /></button>
                <button onClick={(e) => { e.stopPropagation(); removeField(f.id); }} className={`rounded-md p-1 ${t.hover}`}><Trash2 size={14} className="text-red-400" /></button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Settings panel */}
      <Card className="p-4 h-fit lg:sticky lg:top-20">
        {!selected ? (
          <p className={`text-xs ${t.subtext}`}>Sélectionnez un champ pour modifier ses paramètres.</p>
        ) : (
          <div className="space-y-4">
            <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext}`}>Paramètres du champ</p>
            <Field label="Libellé">
              <input
                className={inputCls(t)}
                value={selected.label}
                onChange={(e) => setFields(fields.map((f) => (f.id === selected.id ? { ...f, label: e.target.value } : f)))}
              />
            </Field>
            <Toggle
              label="Champ obligatoire"
              checked={selected.required}
              onChange={(v) => setFields(fields.map((f) => (f.id === selected.id ? { ...f, required: v } : f)))}
            />
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---- Step 3: paramètres avancés ---- */

function StepAdvanced({ form, setForm }) {
  const t = useT();
  const s = form.advanced;
  const setS = (k) => (v) => setForm({ ...form, advanced: { ...s, [k]: v } });

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <Card className="p-5 sm:p-6 divide-y divide-black/5">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} pb-2`}>Inscriptions</p>
        <Toggle label="Inscriptions ouvertes" sub="Activer ou désactiver les nouvelles inscriptions" checked={s.open} onChange={setS("open")} />
        <Toggle label="Limiter le nombre de participants" sub="Basé sur le maximum défini à l'étape 1" checked={s.limit} onChange={setS("limit")} />
        <Toggle label="Liste d'attente" sub="Ajouter les excédents à une file d'attente" checked={s.waitlist} onChange={setS("waitlist")} />
      </Card>

      <Card className="p-5 sm:p-6 divide-y divide-black/5">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} pb-2`}>Notifications</p>
        <Toggle label="Email de confirmation" sub="Envoyé automatiquement après inscription" checked={s.emailConfirm} onChange={setS("emailConfirm")} />
        <Toggle label="Notification Glory2YahPub" sub="Alerte dans l'application pour l'inscrit" checked={s.appNotif} onChange={setS("appNotif")} />
      </Card>

      <Card className="p-5 sm:p-6 divide-y divide-black/5">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} pb-2`}>Identité de l'inscrit</p>
        <Toggle label="QR Code automatique" sub="Généré pour chaque inscrit, scannable à l'entrée" checked={s.qrcode} onChange={setS("qrcode")} />
        <Toggle label="Badge numérique" sub="Badge personnalisé téléchargeable" checked={s.badge} onChange={setS("badge")} />
        <Toggle label="Numéro d'inscription unique" sub="Format REG-XXXX" checked={s.regNumber} onChange={setS("regNumber")} />
      </Card>

      <Card className="p-5 sm:p-6 space-y-4">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext}`}>Apparence</p>
        <Field label="Couleurs du formulaire">
          <div className="flex items-center gap-2">
            {[ACCENT, GOLD, "#0F172A", "#059669", "#DC2626"].map((c) => (
              <button
                key={c}
                onClick={() => setS("color")(c)}
                className="h-8 w-8 rounded-full border-2"
                style={{ background: c, borderColor: s.color === c ? (t.dark ? "#fff" : "#111") : "transparent" }}
              />
            ))}
          </div>
        </Field>
        <Field label="Logo de l'événement">
          <GhostButton icon={Upload} full>Importer un logo</GhostButton>
        </Field>
        <Field label="Image d'arrière-plan">
          <GhostButton icon={ImageIcon} full>Importer une image</GhostButton>
        </Field>

        {/* seal preview - signature element */}
        <div className={`mt-2 flex items-center gap-3 rounded-xl border ${t.border} p-3`}>
          <div
            className="h-12 w-12 rounded-full flex items-center justify-center shrink-0"
            style={{ background: `conic-gradient(from 180deg, ${GOLD_LIGHT}, ${GOLD}, ${GOLD_LIGHT})`, boxShadow: `0 0 0 3px ${t.dark ? "#1A1E2E" : "#fff"}, 0 0 0 4px ${GOLD}55` }}
          >
            <BadgeCheck size={18} className="text-white" />
          </div>
          <div className="min-w-0">
            <p className={`text-xs font-semibold ${t.text}`}>Aperçu du sceau d'inscription</p>
            <p className={`text-[11px] font-mono ${t.subtext}`}>REG-0931 · QR + badge liés au profil</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

/* ---- Step 4: partage ---- */

function StepShare({ form }) {
  const t = useT();
  const link = "https://forms.glory2yahpub.com/e/convention-jeunesse-2026";
  const shareBtns = [
    { label: "WhatsApp", short: "WA", color: "#25D366" },
    { label: "Facebook", short: "FB", color: "#1877F2" },
    { label: "Telegram", short: "TG", color: "#229ED9" },
    { label: "X", short: "X", color: "#111111" },
  ];

  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <Card className="p-5 sm:p-6 space-y-5">
        <div>
          <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} mb-2`}>Lien public</p>
          <div className={`flex items-center gap-2 rounded-xl border ${t.border} ${t.inputBg} px-3 py-2.5`}>
            <Link2 size={15} className={t.subtext} />
            <span className={`text-sm font-mono truncate flex-1 ${t.text}`}>{link}</span>
            <GhostButton icon={Copy} className="!px-2.5 !py-1.5" />
          </div>
        </div>

        <div>
          <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} mb-2`}>Partager</p>
          <div className="grid grid-cols-4 gap-2">
            {shareBtns.map((b) => (
              <button key={b.label} className="flex flex-col items-center gap-1.5 rounded-xl border py-3 hover:opacity-90 transition" style={{ borderColor: `${b.color}33` }}>
                <span className="h-9 w-9 rounded-full flex items-center justify-center text-white text-xs font-bold" style={{ background: b.color }}>{b.short}</span>
                <span className={`text-[11px] ${t.subtext}`}>{b.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} mb-2`}>Code d'intégration (Embed)</p>
          <div className={`rounded-xl border ${t.border} ${t.inputBg} p-3 font-mono text-[11px] ${t.subtext} overflow-x-auto`}>
            {`<iframe src="${link}" width="100%" height="720"></iframe>`}
          </div>
        </div>
      </Card>

      <Card className="p-5 sm:p-6 flex flex-col items-center justify-center text-center gap-3">
        <div className={`h-40 w-40 rounded-2xl border ${t.border} flex items-center justify-center`}>
          <QrCode size={96} className={t.text} />
        </div>
        <p className={`text-sm font-semibold ${t.text}`}>QR Code du formulaire</p>
        <p className={`text-xs ${t.subtext} max-w-xs`}>À imprimer sur vos affiches ou à scanner directement pour rejoindre l'inscription.</p>
        <GhostButton icon={Download}>Télécharger le QR Code</GhostButton>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Réponses reçues                                                        */
/* ---------------------------------------------------------------------- */

function statusTone(s) {
  if (s === "Présent") return "ok";
  if (s === "Absent") return "warn";
  return "neutral";
}

function Responses() {
  const t = useT();
  const [query, setQuery] = useState("");
  const rows = SAMPLE_RESPONSES.filter((r) => r.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className={`flex items-center gap-2 rounded-xl border ${t.border} ${t.inputBg} px-3 py-2 flex-1 min-w-[200px]`}>
          <Search size={16} className={t.subtext} />
          <input placeholder="Rechercher un participant…" value={query} onChange={(e) => setQuery(e.target.value)} className={`bg-transparent outline-none text-sm w-full ${t.text}`} />
        </div>
        <GhostButton icon={Filter}>Date</GhostButton>
        <GhostButton icon={Filter}>Statut</GhostButton>
        <GhostButton icon={ScanLine}>Scanner un QR Code</GhostButton>
      </div>

      <div className="flex flex-wrap gap-2">
        <GhostButton icon={FileSpreadsheet}>Excel</GhostButton>
        <GhostButton icon={FileDown}>PDF</GhostButton>
        <GhostButton icon={FileDown}>CSV</GhostButton>
        <GhostButton icon={Printer}>Imprimer</GhostButton>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className={`text-left ${t.subtext} text-xs uppercase tracking-wide border-b ${t.border}`}>
              <th className="px-4 py-3 font-medium">N°</th>
              <th className="px-4 py-3 font-medium">Nom</th>
              <th className="px-4 py-3 font-medium">Contact</th>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Statut</th>
              <th className="px-4 py-3 font-medium text-right">Présence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`border-b ${t.border} last:border-0`}>
                <td className={`px-4 py-3 font-mono text-xs ${t.subtext}`}>{r.id}</td>
                <td className={`px-4 py-3 font-medium ${t.text}`}>{r.name}</td>
                <td className={`px-4 py-3 ${t.subtext} text-xs`}>{r.email}<br />{r.phone}</td>
                <td className={`px-4 py-3 ${t.subtext} text-xs`}>{r.date}</td>
                <td className="px-4 py-3"><Pill tone={statusTone(r.status)}>{r.status}</Pill></td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1.5">
                    <button className={`rounded-lg p-1.5 ${t.hover}`}><UserCheck size={15} className="text-emerald-500" /></button>
                    <button className={`rounded-lg p-1.5 ${t.hover}`}><UserX size={15} className="text-red-400" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Statistiques                                                           */
/* ---------------------------------------------------------------------- */

function Stats() {
  const t = useT();
  const cards = [
    { label: "Inscriptions totales", value: "342", icon: Users },
    { label: "Taux de complétion", value: "91%", icon: BarChart3 },
    { label: "Présents à l'entrée", value: "288", icon: UserCheck },
    { label: "Sur liste d'attente", value: "12", icon: Clock },
  ];
  const days = [12, 22, 18, 35, 48, 60, 44];
  const max = Math.max(...days);

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {cards.map((c) => (
          <Card key={c.label} className="p-4">
            <c.icon size={16} style={{ color: ACCENT }} />
            <p className={`font-display text-2xl font-semibold mt-2 ${t.text}`}>{c.value}</p>
            <p className={`text-xs ${t.subtext} mt-0.5`}>{c.label}</p>
          </Card>
        ))}
      </div>

      <Card className="p-5 sm:p-6">
        <p className={`text-sm font-semibold ${t.text} mb-4`}>Inscriptions des 7 derniers jours</p>
        <div className="flex items-end gap-3 h-40">
          {days.map((d, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-2">
              <div
                className="w-full rounded-t-lg"
                style={{ height: `${(d / max) * 100}%`, background: `linear-gradient(180deg, ${GOLD_LIGHT}, ${ACCENT})` }}
              />
              <span className={`text-[10px] ${t.subtext}`}>J{i + 1}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Paramètres du module                                                   */
/* ---------------------------------------------------------------------- */

function ModuleSettings() {
  const t = useT();
  const [integrations, setIntegrations] = useState({ payment: true, broadcast: true, certificates: false, community: true });
  const setI = (k) => (v) => setIntegrations({ ...integrations, [k]: v });

  return (
    <div className="p-4 sm:p-6 grid lg:grid-cols-2 gap-5">
      <Card className="p-5 sm:p-6 divide-y divide-black/5">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext} pb-2`}>Intégration Glory2YahPub</p>
        <Toggle label="Module de paiement" sub="Inscriptions payantes et billetterie" checked={integrations.payment} onChange={setI("payment")} />
        <Toggle label="Module de diffusion" sub="Annoncer les nouveaux formulaires en direct" checked={integrations.broadcast} onChange={setI("broadcast")} />
        <Toggle label="Module de certificats" sub="Délivrer un certificat après l'événement" checked={integrations.certificates} onChange={setI("certificates")} />
        <Toggle label="Gestion communautaire" sub="Synchroniser les inscrits avec les groupes" checked={integrations.community} onChange={setI("community")} />
      </Card>

      <Card className="p-5 sm:p-6 space-y-4">
        <p className={`text-xs font-semibold uppercase tracking-wide ${t.subtext}`}>Marque par défaut</p>
        <Field label="Couleur principale">
          <div className="flex gap-2">
            {[ACCENT, GOLD].map((c) => <span key={c} className="h-8 w-8 rounded-full" style={{ background: c }} />)}
          </div>
        </Field>
        <Field label="Nom de l'organisation"><input className={inputCls(t)} defaultValue="Glory2YahPub" /></Field>
        <Field label="Email d'envoi des notifications"><input className={inputCls(t)} defaultValue="notifications@glory2yahpub.com" /></Field>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Assistant IA                                                           */
/* ---------------------------------------------------------------------- */

function AIPanel({ onClose, setFields, setForm }) {
  const t = useT();
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);

  const generate = () => {
    setLoading(true);
    setTimeout(() => {
      setFields([
        { id: "ai1", type: "fullname", label: "Nom complet", required: true },
        { id: "ai2", type: "email", label: "Email", required: true },
        { id: "ai3", type: "phone", label: "Téléphone", required: true },
        { id: "ai4", type: "church", label: "Église", required: false },
        { id: "ai5", type: "mcq", label: "Groupe d'âge", required: false },
      ]);
      setForm((f) => ({ ...f, description: f.description || "Un moment de rassemblement, d'enseignement et de communion pour toute la communauté." }));
      setLoading(false);
      onClose();
    }, 900);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4">
      <Card className="w-full sm:max-w-lg p-5 sm:p-6 rounded-t-2xl sm:rounded-2xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full flex items-center justify-center" style={{ background: `linear-gradient(135deg, ${GOLD_LIGHT}, ${GOLD})` }}>
              <Sparkles size={15} className="text-white" />
            </div>
            <p className={`font-display font-semibold ${t.text}`}>Assistant IA</p>
          </div>
          <button onClick={onClose} className={`rounded-lg p-1.5 ${t.hover}`}><X size={16} className={t.subtext} /></button>
        </div>
        <p className={`text-xs ${t.subtext}`}>Décrivez votre événement, l'IA suggère les champs, corrige les fautes et génère une description professionnelle.</p>
        <textarea
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ex : Convention jeunesse de 3 jours, 500 participants, avec ateliers et hébergement…"
          className={inputCls(t)}
        />
        <PrimaryButton icon={loading ? undefined : Wand2} onClick={generate} full>
          {loading ? "Génération en cours…" : "Générer le formulaire"}
        </PrimaryButton>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* App root                                                                */
/* ---------------------------------------------------------------------- */

export default function App() {
  const [dark, setDark] = useState(false);
  const [screen, setScreen] = useState("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);

  const [form, setForm] = useState({
    name: "", description: "", date: "", time: "", location: "",
    organizer: "", category: "Convention", max: "", deadline: "",
    advanced: {
      open: true, limit: true, waitlist: false, emailConfirm: true, appNotif: true,
      qrcode: true, badge: false, regNumber: true, color: ACCENT,
    },
  });
  const [fields, setFields] = useState(DEFAULT_FIELDS);

  const t = {
    dark,
    toggle: () => setDark((d) => !d),
    bg: dark ? "bg-[#0B0E17]" : "bg-[#FAFAF9]",
    card: dark ? "bg-[#151928] border-white/10" : "bg-white border-black/5",
    sidebar: dark ? "bg-[#0B0E17] border-white/10" : "bg-white border-black/5",
    border: dark ? "border-white/10" : "border-black/10",
    inputBg: dark ? "bg-[#0F1320]" : "bg-white",
    text: dark ? "text-gray-100" : "text-gray-900",
    subtext: dark ? "text-gray-400" : "text-gray-500",
    hover: dark ? "hover:bg-white/5" : "hover:bg-gray-50",
  };

  const titles = {
    dashboard: ["Tableau de bord", "Vue d'ensemble de vos formulaires"],
    myforms: ["Mes formulaires", "Gérez tous vos formulaires d'événement"],
    stats: ["Statistiques", "Suivi des inscriptions en temps réel"],
    responses: ["Réponses reçues", "Gérez et exportez la liste des inscrits"],
    settings: ["Paramètres", "Configuration du module et intégrations"],
    "builder-1": ["Nouveau formulaire", "Étape 1 · Informations générales"],
    "builder-2": ["Nouveau formulaire", "Étape 2 · Constructeur de formulaire"],
    "builder-3": ["Nouveau formulaire", "Étape 3 · Paramètres avancés"],
    "builder-4": ["Nouveau formulaire", "Étape 4 · Partage & publication"],
  };
  const [title, subtitle] = titles[screen] || titles.dashboard;

  return (
    <ThemeCtx.Provider value={t}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        .font-display { font-family: 'Fraunces', serif; }
        * { font-family: 'Inter', sans-serif; }
        .font-mono, code { font-family: 'JetBrains Mono', monospace; }
      `}</style>
      <div className={`min-h-screen ${t.bg} flex`}>
        <Sidebar screen={screen} setScreen={setScreen} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
        <div className="flex-1 min-w-0 flex flex-col">
          <Topbar title={title} subtitle={subtitle} setMobileOpen={setMobileOpen} />
          <main className="flex-1 min-w-0">
            {screen === "dashboard" && <Dashboard setScreen={setScreen} />}
            {screen === "myforms" && <MyForms setScreen={setScreen} />}
            {screen === "stats" && <Stats />}
            {screen === "responses" && <Responses />}
            {screen === "settings" && <ModuleSettings />}
            {screen.startsWith("builder-") && (
              <Builder screen={screen} setScreen={setScreen} form={form} setForm={setForm} fields={fields} setFields={setFields} />
            )}
          </main>
        </div>
      </div>
    </ThemeCtx.Provider>
  );
}
