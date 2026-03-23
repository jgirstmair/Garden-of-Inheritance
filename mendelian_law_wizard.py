"""
Mendelian Law Unlock Wizard

A step-by-step dialog that guides the player through specifying which traits
demonstrate a Mendelian law, then validates their claim against the archive.

Usage:
    from mendelian_law_wizard import MendelianLawWizard
    MendelianLawWizard(parent_window, app)
"""

import tkinter as tk


class MendelianLawWizard(tk.Toplevel):
    """
    Step-by-step wizard for unlocking Mendelian laws.

    Page 1 – Law selection: three large radio-card buttons, each showing the
              law name and a short description.
    Page 2 – Trait selection: the player picks a dominant/recessive value icon
              for each trait pair required by the chosen law.

    After confirming selections the wizard calls test_mendelian_laws and checks
    whether the player's chosen trait(s) match the detected evidence.
    """

    # ── colour palette — inspired by Mendel's handwritten notebook ───────────
    # Warm aged parchment background, sepia ink, rust/terracotta accent.
    BG            = "#F2E6C8"   # aged parchment
    BG_CARD       = "#FAF4E0"   # lighter cream for cards
    BG_CARD_SEL   = "#E8D9B0"   # slightly darker parchment for selected card
    BORDER        = "#5C3D1E"   # dark sepia ink
    BORDER_LIGHT  = "#B89B72"   # warm medium brown
    ACCENT        = "#7D3C1A"   # terracotta / rust (replaces generic green)
    GOLD          = "#A07830"   # warm amber
    GOLD_LIGHT    = "#F5E8C0"   # pale warm cream
    SILVER        = "#7A6850"   # muted warm brown (replaces cold grey)
    SILVER_LIGHT  = "#EDE4D0"   # light warm beige
    TEXT_DARK     = "#2D1A0A"   # near-black sepia ink
    TEXT_MUTED    = "#7A6040"   # faded sepia
    BTN_BG        = "#E8D9B8"   # warm parchment button
    BTN_ACTIVE    = "#D8C8A0"   # slightly darker on hover
    BTN_PRIMARY   = "#7D3C1A"   # terracotta primary action
    BTN_PRIMARY_FG= "#FAF4E0"   # cream text on primary button

    FONT          = ("Segoe UI", 10)
    FONT_BOLD     = ("Segoe UI", 10, "bold")
    FONT_HEADING  = ("Segoe UI", 12, "bold")
    FONT_TITLE    = ("Segoe UI", 14, "bold")
    FONT_SMALL    = ("Segoe UI", 9)
    FONT_TINY     = ("Segoe UI", 8)

    # ── law definitions ───────────────────────────────────────────────────────
    LAWS = [
        {
            "num": 1,
            "name": "Law of Dominance",
            "icon": "⚪",
            "pairs_needed": 1,
            "pair_label": ["Trait pair"],
            "desc": (
                "When two true-breeding plants with contrasting traits are crossed, "
                "all F1 offspring show only one trait — the dominant one. The other "
                "trait (recessive) seems to vanish but is still carried silently."
            ),
        },
        {
            "num": 2,
            "name": "Law of Segregation",
            "icon": "⚫",
            "pairs_needed": 1,
            "pair_label": ["Trait pair"],
            "desc": (
                "Each plant carries two alleles per trait. These separate during "
                "gamete formation. In F2 offspring (after F1 self-pollination) the "
                "recessive trait reappears — about 1 in 4 plants shows it (~3:1 ratio)."
            ),
        },
        {
            "num": 3,
            "name": "Law of Independent Assortment",
            "icon": "🔲",
            "pairs_needed": 2,
            "pair_label": ["First trait pair", "Second trait pair"],
            "desc": (
                "Alleles for different traits segregate independently. Crossing "
                "F1 dihybrids produces four phenotype combinations in F2 offspring "
                "at an approximately 9:3:3:1 ratio."
            ),
        },
    ]

    # ── observable traits (key, label, dominant value, recessive value) ───────
    TRAITS = [
        ("flower_color",    "Flower\nColor",    "purple",   "white"),
        ("flower_position", "Flower\nPosition", "axial",    "terminal"),
        ("pod_color",       "Pod\nColor",       "green",    "yellow"),
        ("pod_shape",       "Pod\nShape",       "inflated", "constricted"),
        ("seed_color",      "Seed\nColor",      "yellow",   "green"),
        ("seed_shape",      "Seed\nShape",      "round",    "wrinkled"),
        ("plant_height",    "Plant\nHeight",    "tall",     "short"),
    ]

    # ── how each trait value is displayed ────────────────────────────────────
    VALUE_LABELS = {
        "purple":       "Purple",
        "white":        "White",
        "axial":        "Axial",
        "terminal":     "Terminal",
        "green":        "Green",
        "yellow":       "Yellow",
        "inflated":     "Inflated",
        "constricted":  "Constricted",
        "round":        "Round",
        "wrinkled":     "Wrinkled",
        "tall":         "Tall",
        "short":        "Dwarf",
    }

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app   = app
        self._imgs = {}          # keep PhotoImage references alive

        self.title("Mendelian Law Discovery")
        self.resizable(False, False)
        self.configure(bg=self.BG)

        # ── runtime state ────────────────────────────────────────────────────
        self._law_var  = tk.IntVar(value=1)   # selected law number (1/2/3)
        # selections[pair_idx] = {"dominant": (trait_key, value) | None,
        #                         "recessive": (trait_key, value) | None}
        self._sels = [{"dominant": None, "recessive": None},
                      {"dominant": None, "recessive": None}]
        self._mode     = "dominant"  # which slot the next click fills
        self._pair_idx = 0           # which pair (Law 3 only)

        # ── pages (Frames, only one shown at a time) ─────────────────────────
        self._page1 = tk.Frame(self, bg=self.BG)
        self._page2 = tk.Frame(self, bg=self.BG)
        self._build_page1()
        self._build_page2()
        self._show_page(1)

        # ── centre on parent ─────────────────────────────────────────────────
        self.update_idletasks()
        W, H = 720, 740
        px = parent.winfo_rootx() + max(0, (parent.winfo_width()  - W) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - H) // 2)
        self.geometry(f"{W}x{H}+{px}+{py}")
        self.transient(parent)
        self.grab_set()

    # ── page helpers ──────────────────────────────────────────────────────────

    def _show_page(self, n):
        self._page1.pack_forget()
        self._page2.pack_forget()
        if n == 1:
            self._page1.pack(fill="both", expand=True)
        else:
            self._page2.pack(fill="both", expand=True)
            self._refresh_page2()

    # =========================================================================
    # Page 1 – Law selection
    # =========================================================================

    def _build_page1(self):
        p = self._page1

        # title bar
        hdr = tk.Frame(p, bg=self.ACCENT, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Mendelian Law Discovery",
                 font=self.FONT_TITLE, bg=self.ACCENT, fg="white").pack()

        tk.Label(p, text="Which Mendelian law would you like to test?",
                 font=self.FONT_HEADING, bg=self.BG, fg=self.TEXT_DARK
                 ).pack(pady=(14, 6), padx=20, anchor="w")

        # cards for each law
        cards_frame = tk.Frame(p, bg=self.BG)
        cards_frame.pack(fill="x", padx=20)
        self._p1_cards = []
        for law in self.LAWS:
            self._p1_cards.append(
                self._make_law_card(cards_frame, law))

        self._refresh_law_cards()

        # separator
        tk.Frame(p, height=1, bg=self.BORDER_LIGHT).pack(fill="x", padx=20, pady=(14, 0))

        # navigation
        nav = tk.Frame(p, bg=self.BG)
        nav.pack(fill="x", padx=20, pady=14)
        tk.Button(nav, text="Cancel",
                  font=self.FONT_BOLD, bg=self.BTN_BG,
                  activebackground=self.BTN_ACTIVE,
                  relief="flat", bd=0, padx=14, pady=6,
                  command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(nav, text="Next  →",
                  font=self.FONT_BOLD,
                  bg=self.BTN_PRIMARY, fg=self.BTN_PRIMARY_FG,
                  activebackground="#5C2810",
                  activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=6,
                  command=lambda: self._show_page(2)).pack(side="right")

    def _make_law_card(self, parent, law):
        """Create a clickable card for one law. Returns the outer frame."""
        outer = tk.Frame(parent, bg=self.BG, pady=4)
        outer.pack(fill="x")

        card = tk.Frame(outer, bg=self.BG_CARD, padx=12, pady=10,
                        highlightthickness=2)
        card.pack(fill="x")

        row = tk.Frame(card, bg=self.BG_CARD)
        row.pack(fill="x")

        rb = tk.Radiobutton(row, variable=self._law_var, value=law["num"],
                            bg=self.BG_CARD, activebackground=self.BG_CARD,
                            command=self._refresh_law_cards)
        rb.pack(side="left")

        name_lbl = tk.Label(row, text=law["name"],
                            font=self.FONT_HEADING, bg=self.BG_CARD,
                            fg=self.TEXT_DARK, cursor="hand2")
        name_lbl.pack(side="left")

        desc_lbl = tk.Label(card, text=law["desc"],
                            font=self.FONT, bg=self.BG_CARD,
                            fg=self.TEXT_MUTED, wraplength=480,
                            justify="left", anchor="w")
        desc_lbl.pack(fill="x", pady=(4, 0))

        # clicking anywhere on card selects the radio
        for w in (card, row, name_lbl, desc_lbl):
            w.bind("<Button-1>", lambda e, n=law["num"]: self._select_law(n))

        return (card, law["num"])

    def _select_law(self, num):
        self._law_var.set(num)
        self._refresh_law_cards()

    def _refresh_law_cards(self):
        sel = self._law_var.get()
        for card, num in self._p1_cards:
            if num == sel:
                card.configure(
                    highlightbackground=self.ACCENT,
                    bg=self.BG_CARD_SEL)
                for w in card.winfo_children():
                    try:
                        w.configure(bg=self.BG_CARD_SEL)
                    except Exception:
                        pass
                    for ww in w.winfo_children():
                        try:
                            ww.configure(bg=self.BG_CARD_SEL)
                        except Exception:
                            pass
            else:
                card.configure(
                    highlightbackground=self.BORDER_LIGHT,
                    bg=self.BG_CARD)
                for w in card.winfo_children():
                    try:
                        w.configure(bg=self.BG_CARD)
                    except Exception:
                        pass
                    for ww in w.winfo_children():
                        try:
                            ww.configure(bg=self.BG_CARD)
                        except Exception:
                            pass

    # =========================================================================
    # Page 2 – Trait selection
    # =========================================================================

    def _build_page2(self):
        """Build the static skeleton of page 2 (dynamic parts rebuilt in _refresh_page2)."""
        p = self._page2

        # title bar
        self._p2_hdr = tk.Frame(p, bg=self.ACCENT, pady=10)
        self._p2_hdr.pack(fill="x")
        self._p2_title = tk.Label(self._p2_hdr, text="",
                                  font=self.FONT_TITLE, bg=self.ACCENT, fg="white")
        self._p2_title.pack()

        # nav bar (static at bottom, packed before canvas so it stays fixed)
        sep = tk.Frame(p, height=1, bg=self.BORDER_LIGHT)
        sep.pack(fill="x", side="bottom")
        nav = tk.Frame(p, bg=self.BG)
        nav.pack(fill="x", padx=20, pady=10, side="bottom")
        self._p2_back_btn = tk.Button(nav, text="←  Back",
                  font=self.FONT_BOLD, bg=self.BTN_BG,
                  activebackground=self.BTN_ACTIVE,
                  relief="flat", bd=0, padx=14, pady=6,
                  command=self._go_back)
        self._p2_back_btn.pack(side="left")
        tk.Button(nav, text="Cancel",
                  font=self.FONT_BOLD, bg=self.BTN_BG,
                  activebackground=self.BTN_ACTIVE,
                  relief="flat", bd=0, padx=14, pady=6,
                  command=self.destroy).pack(side="right", padx=(8, 0))
        self._p2_unlock_btn = tk.Button(
            nav, text="🔓  Unlock",
            font=self.FONT_BOLD,
            bg=self.BTN_PRIMARY, fg=self.BTN_PRIMARY_FG,
            activebackground="#5C2810", activeforeground=self.BTN_PRIMARY_FG,
            relief="flat", bd=0, padx=14, pady=6,
            state="disabled",
            command=self._on_unlock)
        self._p2_unlock_btn.pack(side="right")

        # scrollable canvas for the body content
        self._p2_canvas_frame = tk.Frame(p, bg=self.BG)
        self._p2_canvas_frame.pack(fill="both", expand=True)

        self._p2_canvas = tk.Canvas(self._p2_canvas_frame, bg=self.BG,
                                    highlightthickness=0)
        scrollbar = tk.Scrollbar(self._p2_canvas_frame, orient="vertical",
                                 command=self._p2_canvas.yview)
        self._p2_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._p2_canvas.pack(side="left", fill="both", expand=True)

        # inner frame that holds all dynamic content
        self._p2_body = tk.Frame(self._p2_canvas, bg=self.BG)
        self._p2_canvas_window = self._p2_canvas.create_window(
            (0, 0), window=self._p2_body, anchor="nw")

        def _on_body_configure(e):
            self._p2_canvas.configure(
                scrollregion=self._p2_canvas.bbox("all"))

        def _on_canvas_configure(e):
            self._p2_canvas.itemconfig(
                self._p2_canvas_window, width=e.width)

        self._p2_body.bind("<Configure>", _on_body_configure)
        self._p2_canvas.bind("<Configure>", _on_canvas_configure)

        # mouse-wheel scrolling (Windows + Linux + macOS)
        def _on_mousewheel(e):
            if e.num == 4:
                self._p2_canvas.yview_scroll(-1, "units")
            elif e.num == 5:
                self._p2_canvas.yview_scroll(1, "units")
            else:
                self._p2_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self._p2_canvas.bind("<MouseWheel>", _on_mousewheel)
        self._p2_canvas.bind("<Button-4>", _on_mousewheel)
        self._p2_canvas.bind("<Button-5>", _on_mousewheel)
        self._p2_body.bind("<MouseWheel>", _on_mousewheel)
        self._p2_body.bind("<Button-4>", _on_mousewheel)
        self._p2_body.bind("<Button-5>", _on_mousewheel)

    def _go_back(self):
        # Clear any lingering result banner
        for w in self._page2.winfo_children():
            if getattr(w, "_is_result_panel", False):
                w.destroy()
        # Restore nav buttons to default state
        try:
            self._p2_back_btn.pack(side="left")
            self._p2_unlock_btn.configure(
                text="🔓  Unlock",
                command=self._on_unlock,
                bg=self.BTN_PRIMARY, fg=self.BTN_PRIMARY_FG,
                state="disabled")
        except Exception:
            pass
        # Reset selections when going back
        self._sels = [{"dominant": None, "recessive": None},
                      {"dominant": None, "recessive": None}]
        self._mode     = "dominant"
        self._pair_idx = 0
        self._show_page(1)

    def _refresh_page2(self):
        """Rebuild the dynamic body of page 2 for the currently selected law."""
        # clear body
        for w in self._p2_body.winfo_children():
            w.destroy()

        law_num  = self._law_var.get()
        law_info = self.LAWS[law_num - 1]

        self._p2_title.configure(text=f"🌿  {law_info['name']}")

        body = self._p2_body
        pairs_needed = law_info["pairs_needed"]

        # reset state
        self._sels = [{"dominant": None, "recessive": None},
                      {"dominant": None, "recessive": None}]
        self._mode     = "dominant"
        self._pair_idx = 0
        self._pairs_needed = pairs_needed

        # ── instruction banner ───────────────────────────────────────────────
        inst_frame = tk.Frame(body, bg="#EDE0C0", padx=14, pady=8,
                              highlightbackground="#B89B72", highlightthickness=1)
        inst_frame.pack(fill="x", padx=20, pady=(12, 0))
        self._p2_inst_lbl = tk.Label(inst_frame, text="",
                                     font=self.FONT_BOLD, bg="#EDE0C0",
                                     fg=self.ACCENT, wraplength=480, justify="left")
        self._p2_inst_lbl.pack(anchor="w")

        # ── selection slots ──────────────────────────────────────────────────
        slots_outer = tk.Frame(body, bg=self.BG)
        slots_outer.pack(fill="x", padx=20, pady=(12, 0))
        self._slot_frames = []

        is_law2 = (law_num == 2)
        is_law3 = (law_num == 3)

        # ── for Law 3: 4 compact boxes matching Law 2's visual style ────────
        if is_law3:
            self._law3_box_labels = []
            self._slot_frames     = []

            # num, pct, box-bg, box-border, a_role, b_role
            BOX_DEFS = [
                ("9", "~56%", "#F0E8D0", self.ACCENT,       "a_dom", "b_dom"),
                ("3", "~19%", "#EDE0C0", self.GOLD,          "a_dom", "b_rec"),
                ("3", "~19%", "#E8D8B8", self.BORDER,        "a_rec", "b_dom"),
                ("1",  "~6%", "#F5EDD8", self.SILVER,        "a_rec", "b_rec"),
            ]

            boxes_row = tk.Frame(slots_outer, bg=self.BG)
            boxes_row.pack(fill="x", pady=(0, 2))

            for num_txt, pct_txt, bg_c, bd_c, a_role, b_role in BOX_DEFS:
                col = tk.Frame(boxes_row, bg=self.BG)
                col.pack(side="left", padx=(0, 10))

                # Number label above box
                tk.Label(col, text=f"{num_txt}  ({pct_txt})",
                         font=self.FONT_TINY, bg=self.BG,
                         fg=bd_c).pack()

                # The 72×72 card – contents rebuilt dynamically in _refresh_slots
                card = tk.Frame(col, bg=bg_c,
                                highlightbackground=bd_c,
                                highlightthickness=2,
                                width=72, height=72)
                card.pack_propagate(False)
                card.pack()

                # Placeholder: big number centred in the empty card
                tk.Label(card, text=num_txt,
                         font=("Segoe UI", 28, "bold"),
                         bg=bg_c, fg=bd_c).pack(expand=True)

                # Value text below card
                ab_val_lbl = tk.Label(col, text="— / —",
                                      font=self.FONT_TINY, bg=self.BG,
                                      fg=self.TEXT_MUTED)
                ab_val_lbl.pack()

                self._law3_box_labels.append({
                    "bg": bg_c, "bd": bd_c,
                    "num_txt": num_txt,
                    "a_role": a_role, "b_role": b_role,
                    "ab_val": ab_val_lbl,
                    "card":  card,
                })

        else:
            # ── Law 1 / Law 2: original pair-row layout ───────────────────────
            self._law3_box_labels = []

            # Slot label text / placeholder numbers vary per law
            if is_law2:
                dom_label_text, dom_label_fg = "3  (75%)", self.ACCENT
                rec_label_text, rec_label_fg = "1  (25%)", self.SILVER
                dom_ph, rec_ph = "3", "1"
            else:
                dom_label_text, dom_label_fg = "Dominant",  self.GOLD
                rec_label_text, rec_label_fg = "Recessive", self.SILVER
                dom_ph, rec_ph = "D", "R"

            for i in range(pairs_needed):
                pair_row = tk.Frame(slots_outer, bg=self.BG)
                pair_row.pack(fill="x", pady=(0, 8))

                # dominant slot
                dom_outer = tk.Frame(pair_row, bg=self.BG)
                dom_outer.pack(side="left", padx=(0, 4))
                tk.Label(dom_outer, text=dom_label_text, font=self.FONT_TINY,
                         bg=self.BG, fg=dom_label_fg).pack()
                dom_card = tk.Frame(dom_outer, bg=self.GOLD_LIGHT,
                                    highlightbackground=self.GOLD if not is_law2 else self.ACCENT,
                                    highlightthickness=2, width=72, height=72)
                dom_card.pack_propagate(False)
                dom_card.pack()
                dom_img_lbl = tk.Label(dom_card, bg=self.GOLD_LIGHT,
                                       text=dom_ph, font=("Segoe UI", 26, "bold"),
                                       fg="#C8A830")
                dom_img_lbl.pack(expand=True)
                dom_val_lbl = tk.Label(dom_outer, text="-",
                                       font=self.FONT_TINY, bg=self.BG, fg=self.TEXT_MUTED)
                dom_val_lbl.pack()

                # separator
                if is_law2:
                    tk.Label(pair_row, text=":", font=("Segoe UI", 28, "bold"),
                             bg=self.BG, fg=self.TEXT_DARK).pack(side="left", padx=6)
                else:
                    tk.Label(pair_row, text="->", font=("Segoe UI", 16),
                             bg=self.BG, fg=self.BORDER_LIGHT).pack(side="left", padx=4)

                # recessive slot
                rec_outer = tk.Frame(pair_row, bg=self.BG)
                rec_outer.pack(side="left", padx=(4, 8))
                tk.Label(rec_outer, text=rec_label_text, font=self.FONT_TINY,
                         bg=self.BG, fg=rec_label_fg).pack()
                rec_card = tk.Frame(rec_outer, bg=self.SILVER_LIGHT,
                                    highlightbackground=self.SILVER,
                                    highlightthickness=2, width=72, height=72)
                rec_card.pack_propagate(False)
                rec_card.pack()
                rec_img_lbl = tk.Label(rec_card, bg=self.SILVER_LIGHT,
                                       text=rec_ph, font=("Segoe UI", 26, "bold"),
                                       fg="#999999")
                rec_img_lbl.pack(expand=True)
                rec_val_lbl = tk.Label(rec_outer, text="-",
                                       font=self.FONT_TINY, bg=self.BG, fg=self.TEXT_MUTED)
                rec_val_lbl.pack()

                self._slot_frames.append(
                    (dom_card, rec_card, dom_val_lbl, rec_val_lbl,
                     dom_img_lbl, rec_img_lbl))

        # ── separator ────────────────────────────────────────────────────────
        tk.Frame(body, height=1, bg=self.BORDER_LIGHT).pack(
            fill="x", padx=20, pady=(8, 6))

        tk.Label(body, text="Click a trait icon to assign it:",
                 font=self.FONT_BOLD, bg=self.BG, fg=self.TEXT_DARK
                 ).pack(padx=20, anchor="w")

        # ── trait icon grid ──────────────────────────────────────────────────
        grid_outer = tk.Frame(body, bg=self.BG)
        grid_outer.pack(fill="x", padx=20, pady=(8, 0))

        self._trait_btn_refs = {}   # (trait_key, value) -> (outer_frame, img_lbl, name_lbl)
        for col_i, (tkey, tlabel, dom_val, rec_val) in enumerate(self.TRAITS):
            col_frame = tk.Frame(grid_outer, bg=self.BG)
            col_frame.grid(row=0, column=col_i, padx=4)

            tk.Label(col_frame, text=tlabel,
                     font=self.FONT_TINY, bg=self.BG,
                     fg=self.TEXT_MUTED, wraplength=80,
                     justify="center").pack(pady=(0, 2))

            for val, is_dom in [(dom_val, True), (rec_val, False)]:
                btn_outer = tk.Frame(col_frame, bg=self.BG,
                                     highlightbackground=self.BORDER_LIGHT,
                                     highlightthickness=1,
                                     padx=2, pady=2,
                                     cursor="hand2")
                btn_outer.pack(pady=2)

                img = self._load_trait_img(tkey, val, size=72)
                img_lbl = tk.Label(btn_outer, image=img,
                                   bg=self.BG, cursor="hand2",
                                   width=72, height=72)
                img_lbl.pack()

                val_lbl = tk.Label(btn_outer,
                                   text=self.VALUE_LABELS.get(val, val),
                                   font=self.FONT_TINY, bg=self.BG,
                                   fg=self.TEXT_DARK, cursor="hand2")
                val_lbl.pack()

                # bind click
                for w in (btn_outer, img_lbl, val_lbl):
                    w.bind("<Button-1>",
                           lambda e, k=tkey, v=val: self._on_trait_click(k, v))
                    # propagate scroll to canvas
                    w.bind("<MouseWheel>", lambda e: self._p2_canvas.yview_scroll(
                        int(-1 * (e.delta / 120)), "units"))
                    w.bind("<Button-4>", lambda e: self._p2_canvas.yview_scroll(-1, "units"))
                    w.bind("<Button-5>", lambda e: self._p2_canvas.yview_scroll(1, "units"))

                self._trait_btn_refs[(tkey, val)] = (btn_outer, img_lbl, val_lbl)

        self._update_instruction()
        self._update_unlock_btn()

    # ── trait icon loading ────────────────────────────────────────────────────

    def _load_trait_img(self, trait_key, value, size=72):
        """Load trait icon scaled to size×size; cache result.

        Uses PIL (ImageTk.PhotoImage) throughout — tkinter's native PhotoImage
        cannot open these icon files reliably (format/encoding incompatibility).
        """
        cache_key = (trait_key, value, size)
        if cache_key in self._imgs:
            return self._imgs[cache_key]

        def _pil_load(path):
            """Open path with PIL, resize to size×size, return ImageTk.PhotoImage."""
            if not path:
                return None
            try:
                from PIL import Image, ImageTk
                pil = Image.open(path).convert("RGBA")
                pil = pil.resize((size, size), Image.LANCZOS)
                img = ImageTk.PhotoImage(pil)
                return img
            except Exception:
                return None

        try:
            from icon_loader import (trait_icon_path, pod_shape_icon_path,
                                     flower_icon_path_hi, flower_icon_path)

            # ── pod_shape ────────────────────────────────────────────────────
            # pod_shape_icon_path() needs shape + color; try both pod colors.
            if trait_key == "pod_shape":
                for pod_color in ("green", "yellow"):
                    img = _pil_load(pod_shape_icon_path(value, pod_color))
                    if img is not None:
                        self._imgs[cache_key] = img
                        return img

            # ── flower_position ──────────────────────────────────────────────
            # flower_icon_path_hi() encodes BOTH position and color in the
            # filename (flower_{pos}_{col}_64x64.png), so None/empty color
            # produces a path that never exists.  Try both valid colors.
            if trait_key == "flower_position":
                for col in ("purple", "white"):
                    img = _pil_load(flower_icon_path_hi(value, col))
                    if img is not None:
                        self._imgs[cache_key] = img
                        return img
                    img = _pil_load(flower_icon_path(value, col))
                    if img is not None:
                        self._imgs[cache_key] = img
                        return img

            # ── generic fallback for all other traits ────────────────────────
            img = _pil_load(trait_icon_path(trait_key, value))
            if img is not None:
                self._imgs[cache_key] = img
                return img

        except Exception:
            pass

        # last-resort blank image
        try:
            img = tk.PhotoImage(width=size, height=size)
            self._imgs[cache_key] = img
            return img
        except Exception:
            return None


    # ── instruction label ─────────────────────────────────────────────────────

    def _update_instruction(self):
        law_num  = self._law_var.get()
        pairs_n  = self.LAWS[law_num - 1]["pairs_needed"]
        pair_lbl = self.LAWS[law_num - 1]["pair_label"]

        if pairs_n == 1:
            if self._mode == "dominant":
                txt = "Step 1: Choose the DOMINANT trait (present in all parent plants)."
            else:
                txt = "Step 2: Select RECESSIVE trait (disappeared in parent plants)."
        else:
            # Law 3: just 2 steps – clicking any icon of a trait fills both slots
            if self._mode == "done":
                txt = "Both traits selected! Click 🔓 Unlock to test."
            elif self._pair_idx == 0:
                txt = ("Step 1: Choose the first trait. ")
            else:
                txt = ("Step 2: Select a second trait. "
                       "It must be different from the first.")

        if hasattr(self, "_p2_inst_lbl"):
            self._p2_inst_lbl.configure(text=txt)

    # ── trait click handler ───────────────────────────────────────────────────

    def _on_trait_click(self, trait_key, value):
        """Assign clicked trait value to current slot."""
        law_num  = self._law_var.get()
        pairs_n  = self.LAWS[law_num - 1]["pairs_needed"]
        pair_idx = self._pair_idx

        if pairs_n == 2:
            # ── Law 3: one click selects the whole trait (dom + rec auto-filled) ──
            if self._mode == "done":
                return  # already complete

            # Reject if this trait is already used by the other pair
            other_pair_idx = 1 - pair_idx
            for role in ("dominant", "recessive"):
                existing = self._sels[other_pair_idx][role]
                if existing and existing[0] == trait_key:
                    return

            # Look up canonical dom/rec values from TRAITS definition
            trait_info = next((t for t in self.TRAITS if t[0] == trait_key), None)
            if not trait_info:
                return
            _, _, dom_val, rec_val = trait_info

            self._sels[pair_idx]["dominant"]  = (trait_key, dom_val)
            self._sels[pair_idx]["recessive"] = (trait_key, rec_val)

            # Advance to next pair or mark done
            next_pair = pair_idx + 1
            if next_pair < pairs_n:
                self._pair_idx = next_pair
            else:
                self._mode = "done"

        else:
            # ── Law 1 / Law 2: original step-by-step logic ────────────────────
            mode       = self._mode
            other_mode = "recessive" if mode == "dominant" else "dominant"

            # Don't allow the exact same icon in both slots of this pair
            other_sel = self._sels[pair_idx][other_mode]
            if other_sel and other_sel == (trait_key, value):
                return

            self._sels[pair_idx][mode] = (trait_key, value)

            if mode == "dominant":
                self._mode = "recessive"
            else:
                next_pair = pair_idx + 1
                if next_pair < pairs_n:
                    self._pair_idx = next_pair
                    self._mode     = "dominant"
                else:
                    self._mode = "done"

        self._refresh_slots()
        self._highlight_used_traits()
        self._update_instruction()
        self._update_unlock_btn()

    def _refresh_slots(self):
        """Update slot cards to show current selections."""
        law_num = self._law_var.get()

        # ── Law 3: rebuild each box's interior based on fill state ─────────
        if law_num == 3 and getattr(self, "_law3_box_labels", None):
            role_to_sel = {
                "a_dom": self._sels[0]["dominant"],
                "a_rec": self._sels[0]["recessive"],
                "b_dom": self._sels[1]["dominant"],
                "b_rec": self._sels[1]["recessive"],
            }
            for box_info in self._law3_box_labels:
                bg   = box_info["bg"]
                bd   = box_info["bd"]
                num  = box_info["num_txt"]
                card = box_info["card"]
                a_sel = role_to_sel.get(box_info["a_role"])
                b_sel = role_to_sel.get(box_info["b_role"])

                # Clear current card contents
                for w in card.winfo_children():
                    w.destroy()

                if not a_sel and not b_sel:
                    # ── Empty: big number fills the whole card ────────────────
                    tk.Label(card, text=num,
                             font=("Segoe UI", 28, "bold"),
                             bg=bg, fg=bd).pack(expand=True)

                elif a_sel and b_sel:
                    # ── Both traits selected: two icons side by side ──────────
                    inner = tk.Frame(card, bg=bg)
                    inner.place(relx=0.5, rely=0.5, anchor="center")

                    img_a = self._load_trait_img(*a_sel, size=28)
                    a_lbl = tk.Label(inner, bg=bg, width=28, height=28)
                    if img_a:
                        a_lbl.configure(image=img_a, text="")
                        a_lbl.image = img_a  # prevent GC
                    else:
                        a_lbl.configure(text="A", font=("Segoe UI", 13, "bold"), fg=bd)
                    a_lbl.pack(side="left", padx=2)

                    tk.Frame(inner, width=1, bg=bd).pack(side="left", fill="y", pady=4)

                    img_b = self._load_trait_img(*b_sel, size=28)
                    b_lbl = tk.Label(inner, bg=bg, width=28, height=28)
                    if img_b:
                        b_lbl.configure(image=img_b, text="")
                        b_lbl.image = img_b  # prevent GC
                    else:
                        b_lbl.configure(text="B", font=("Segoe UI", 13, "bold"), fg=self.BORDER)
                    b_lbl.pack(side="left", padx=2)

                else:
                    # ── One trait selected: icon on filled side, small num on empty ──
                    inner = tk.Frame(card, bg=bg)
                    inner.place(relx=0.5, rely=0.5, anchor="center")

                    if a_sel:
                        img_a = self._load_trait_img(*a_sel, size=28)
                        a_lbl = tk.Label(inner, bg=bg, width=28, height=28)
                        if img_a:
                            a_lbl.configure(image=img_a, text="")
                            a_lbl.image = img_a  # prevent GC
                        else:
                            a_lbl.configure(text="A", font=("Segoe UI", 13, "bold"), fg=bd)
                        a_lbl.pack(side="left", padx=2)
                        tk.Frame(inner, width=1, bg=bd).pack(side="left", fill="y", pady=4)
                        tk.Label(inner, text=num, font=("Segoe UI", 13, "bold"),
                                 bg=bg, fg=self.BORDER, width=2).pack(side="left", padx=2)
                    else:
                        tk.Label(inner, text=num, font=("Segoe UI", 13, "bold"),
                                 bg=bg, fg=bd, width=2).pack(side="left", padx=2)
                        tk.Frame(inner, width=1, bg=bd).pack(side="left", fill="y", pady=4)
                        img_b = self._load_trait_img(*b_sel, size=28)
                        b_lbl = tk.Label(inner, bg=bg, width=28, height=28)
                        if img_b:
                            b_lbl.configure(image=img_b, text="")
                            b_lbl.image = img_b  # prevent GC
                        else:
                            b_lbl.configure(text="B", font=("Segoe UI", 13, "bold"), fg=self.BORDER)
                        b_lbl.pack(side="left", padx=2)

                # Value label below card
                a_name = self.VALUE_LABELS.get(a_sel[1], a_sel[1]) if a_sel else "—"
                b_name = self.VALUE_LABELS.get(b_sel[1], b_sel[1]) if b_sel else "—"
                box_info["ab_val"].configure(text=f"{a_name} / {b_name}")
            return

        # ── Law 1 / Law 2: update the original dominant/recessive slots ───────
        is_law2 = (law_num == 2)
        dom_ph  = "3" if is_law2 else "?"
        rec_ph  = "1" if is_law2 else "?"

        for i, (dom_card, rec_card,
                dom_val_lbl, rec_val_lbl,
                dom_img_lbl, rec_img_lbl) in enumerate(self._slot_frames):

            dom_sel = self._sels[i]["dominant"]
            rec_sel = self._sels[i]["recessive"]

            # dominant slot
            if dom_sel:
                img = self._load_trait_img(*dom_sel, size=52)
                if img:
                    dom_img_lbl.configure(image=img, text="")
                dom_val_lbl.configure(
                    text=self.VALUE_LABELS.get(dom_sel[1], dom_sel[1]),
                    fg=self.GOLD)
                dom_card.configure(bg="#F5E8C0")
                dom_img_lbl.configure(bg="#F5E8C0")
            else:
                dom_img_lbl.configure(text=dom_ph, image="", fg=self.GOLD)
                dom_val_lbl.configure(text="—", fg=self.TEXT_MUTED)
                dom_card.configure(bg=self.GOLD_LIGHT)
                dom_img_lbl.configure(bg=self.GOLD_LIGHT)

            # recessive slot
            if rec_sel:
                img = self._load_trait_img(*rec_sel, size=52)
                if img:
                    rec_img_lbl.configure(image=img, text="")
                rec_val_lbl.configure(
                    text=self.VALUE_LABELS.get(rec_sel[1], rec_sel[1]),
                    fg=self.SILVER)
                rec_card.configure(bg="#EDE4D0")
                rec_img_lbl.configure(bg="#EDE4D0")
            else:
                rec_img_lbl.configure(text=rec_ph, image="", fg=self.SILVER)
                rec_val_lbl.configure(text="—", fg=self.TEXT_MUTED)
                rec_card.configure(bg=self.SILVER_LIGHT)
                rec_img_lbl.configure(bg=self.SILVER_LIGHT)

    def _highlight_used_traits(self):
        """Dim trait buttons that have already been selected."""
        used = set()
        for sel in self._sels:
            for role in ("dominant", "recessive"):
                v = sel[role]
                if v:
                    used.add(v)

        for (tkey, val), (outer, img_lbl, val_lbl) in self._trait_btn_refs.items():
            if (tkey, val) in used:
                outer.configure(bg="#D8C8A8",
                                highlightbackground="#B8A888")
                img_lbl.configure(bg="#D8C8A8")
                val_lbl.configure(bg="#D8C8A8", fg="#9A8060")
            else:
                outer.configure(bg=self.BG,
                                highlightbackground=self.BORDER_LIGHT)
                img_lbl.configure(bg=self.BG)
                val_lbl.configure(bg=self.BG, fg=self.TEXT_DARK)

    def _update_unlock_btn(self):
        """Enable Unlock button only when all required slots are filled."""
        law_num  = self._law_var.get()
        pairs_n  = self.LAWS[law_num - 1]["pairs_needed"]
        ready = all(
            self._sels[i]["dominant"] and self._sels[i]["recessive"]
            for i in range(pairs_n)
        )
        if hasattr(self, "_p2_unlock_btn"):
            self._p2_unlock_btn.configure(
                state="normal" if ready else "disabled",
                bg=self.BTN_PRIMARY if ready else "#B8A888",
                fg="white")

    # =========================================================================
    # Unlock action
    # =========================================================================

    def _on_unlock(self):
        app     = self.app
        law_num = self._law_var.get()

        # ── sync archive ──────────────────────────────────────────────────────
        try:
            if hasattr(app, "_seed_archive_safe"):
                app._seed_archive_safe()
        except Exception:
            pass

        # ── get selected plant pid ────────────────────────────────────────────
        idx   = getattr(app, "selected_index", None)
        plant = None
        if idx is not None:
            try:
                plant = app.tiles[idx].plant
            except Exception:
                pass

        if not plant:
            self._show_result(False,
                "No plant selected.\n\nSelect a plant in the garden first, then try again.")
            return

        pid = getattr(plant, "id", None)
        if pid is None:
            self._show_result(False, "Selected plant has no ID. Try selecting a different plant.")
            return

        # ── run the law test ──────────────────────────────────────────────────
        try:
            from traitinheritanceexplorer import test_mendelian_laws
            res = test_mendelian_laws(
                app,
                archive=getattr(app, "archive", None),
                pid=pid,
                allow_credit=False,   # wizard validates first; credits manually below
                toast=False,      # wizard handles feedback
                target_law=law_num,  # only credit the law the player is testing
            )
        except Exception as e:
            self._show_result(False, f"Test failed with an error:\n{e}")
            return

        law_key = f"law{law_num}"
        discovered = bool(res.get(law_key, False))

        if not discovered:
            # Build a helpful explanation
            msgs = {
                1: (
                    "No evidence for the Law of Dominance found.\n\n"
                    "Make sure you have selected a plant whose parents were "
                    "both true-breeding with contrasting traits, and that "
                    "> 15 sibling plants show the same (dominant) phenotype."
                ),
                2: (
                    "The Law of Segregation hasn't been demonstrated yet.\n\n"
                    "You need at least 65 offspring showing approximately a 3:1 ratio of "
                    "a 3:1 ratio of dominant to recessive phenotype."
                ),
                3: (
                    "The Law of Independent Assortment hasn't been confirmed yet.\n\n"
                    "You need at least 80 offsprings showing a ~9:3:3:1 "
                    "ratio for two independent traits."
                ),
            }
            self._show_result(False, msgs.get(law_num, "The law conditions were not met yet."))
            return

        # ── validate player's trait selection ─────────────────────────────────
        trait_mismatch = False
        mismatch_msg   = ""

        n  = self._norm_val   # shorthand

        if law_num in (1, 2):
            sel_dom_trait = self._sels[0]["dominant"][0]    # trait key e.g. "flower_color"
            sel_dom_value = self._sels[0]["dominant"][1]    # value    e.g. "purple"
            sel_rec_trait = self._sels[0]["recessive"][0]
            sel_rec_value = self._sels[0]["recessive"][1]

            # Both slots must belong to the same trait
            if sel_dom_trait != sel_rec_trait:
                trait_mismatch = True
                mismatch_msg = (
                    "Your two selections belong to different traits.\n"
                    "Both values must come from the same trait "
                    "(e.g. purple AND white Flower Color)."
                )

            elif law_num == 1:
                valid_pairs = res.get("law1_all_valid") or []
                # fall back to legacy single fields if list is empty
                if not valid_pairs:
                    t = res.get("law1_trait") or ""
                    d = res.get("law1_dominant_value") or ""
                    if t and d:
                        valid_pairs = [(t, d)]

                if valid_pairs:
                    # player's selection must match one of the qualifying (trait, dominant_value) pairs
                    match = any(
                        sel_dom_trait == vt and n(sel_dom_value) == n(vd)
                        for vt, vd in valid_pairs
                    )
                    if not match:
                        # check if they got the trait right but swapped dom/rec
                        trait_match = any(sel_dom_trait == vt for vt, _ in valid_pairs)
                        if not trait_match:
                            trait_mismatch = True
                            mismatch_msg = (
                                "The evidence points to a different trait.\n\n"
                                "Hint: look for a trait where both parents were "
                                "true-breeding (homozygous) with contrasting values "
                                "and all offsprings showed only one phenotype (trait).\n\n"
                                "Try again!"
                            )
                        else:
                            trait_mismatch = True
                            mismatch_msg = (
                                "You have the right trait, but dominant and recessive "
                                "traits are swapped.\n\n"
                                "Try swapping the two icons!"
                            )

            elif law_num == 2:
                valid_pairs = res.get("law2_all_valid") or []
                if not valid_pairs:
                    t = res.get("law2_trait") or ""
                    d = res.get("law2_dominant_value") or ""
                    if t and d:
                        valid_pairs = [(t, d)]

                if valid_pairs:
                    match = any(
                        sel_dom_trait == vt and n(sel_dom_value) == n(vd)
                        for vt, vd in valid_pairs
                    )
                    if not match:
                        trait_match = any(sel_dom_trait == vt for vt, _ in valid_pairs)
                        if not trait_match:
                            trait_mismatch = True
                            mismatch_msg = (
                                "The 3:1 ratio was not observed for this trait.\n\n"
                                "Hint: look at which trait shows roughly 75% of one "
                                "value and 25% of the other in your F2 plants.\n\n"
                                "Try again!"
                            )
                        else:
                            trait_mismatch = True
                            mismatch_msg = (
                                "You are close, but not quite correct.\n\n"
                                "Hint: The value in the '3 (75%)' slot should be the one "
                                "that appears in most offspring.\n\n"
                                "Try swapping the two icons!"
                            )

        elif law_num == 3:
            tk1 = self._sels[0]["dominant"][0]
            tk2 = self._sels[1]["dominant"][0]
            if tk1 == tk2:
                trait_mismatch = True
                mismatch_msg = (
                    "Both trait pairs belong to the same trait.\n"
                    "Independent Assortment requires two different traits."
                )
            else:
                sel_set = frozenset({tk1, tk2})
                valid_pairs = res.get("law3_all_valid_pairs") or []
                valid_sets  = [frozenset(p) for p in valid_pairs]
                # also fall back to legacy single-pair field if new list is empty
                if not valid_sets:
                    detected = res.get("law3_traits")
                    if detected:
                        valid_sets = [frozenset({detected[0], detected[1]})]
                if valid_sets and sel_set not in valid_sets:
                    trait_mismatch = True
                    mismatch_msg = (
                        "The 9:3:3:1 ratio was not observed for this trait pair.\n\n"
                        "Look for two traits that both show 4 phenotype classes "
                        "in your offspring in roughly a 9:3:3:1 ratio.\n\n"
                        "Try again!"
                    )

        if trait_mismatch:
            self._show_result(False, mismatch_msg)
            return

        # ── success! ──────────────────────────────────────────────────────────
        law_name = self.LAWS[law_num - 1]["name"]

        # Credit the law manually (allow_credit=False was passed so it wasn't auto-credited)
        attr = f"law{law_num}_ever_discovered"
        if not getattr(app, attr, False):
            setattr(app, attr, True)
            setattr(app, f"law{law_num}_first_plant", pid)

        try:
            app._toast(f"✔ {law_name} unlocked!", level="info")
        except Exception:
            pass
        try:
            app._update_law_status_label()
        except Exception:
            pass

        # Collect selected trait names for the success message.
        # TRAITS labels use "\n" for the icon grid; replace with space for inline use.
        def _flat(lbl): return lbl.replace("\n", " ").strip()

        dom_val_str = self.VALUE_LABELS.get(self._sels[0]["dominant"][1],
                                             self._sels[0]["dominant"][1])
        rec_val_str = self.VALUE_LABELS.get(self._sels[0]["recessive"][1],
                                             self._sels[0]["recessive"][1])
        trait_name  = _flat(dict((k, lbl) for k, lbl, *_ in self.TRAITS).get(
            self._sels[0]["dominant"][0], self._sels[0]["dominant"][0]))

        if law_num == 2:
            # Update ratio UI to the player-chosen trait, not just the first detected one
            chosen_tk = self._sels[0]["dominant"][0]
            all_ratios = res.get("law2_all_valid_ratios") or {}
            chosen_ratio = all_ratios.get(chosen_tk)
            if chosen_ratio:
                try:
                    app.law2_ratio_ui = chosen_ratio
                    app._update_law_status_label()
                except Exception:
                    pass
            extra = f"\nTrait: {dom_val_str} > {rec_val_str}  ({trait_name})"

        elif law_num == 3:
            dom2_val_str = self.VALUE_LABELS.get(self._sels[1]["dominant"][1],
                                                  self._sels[1]["dominant"][1])
            rec2_val_str = self.VALUE_LABELS.get(self._sels[1]["recessive"][1],
                                                  self._sels[1]["recessive"][1])
            trait_name2  = _flat(dict((k, lbl) for k, lbl, *_ in self.TRAITS).get(
                self._sels[1]["dominant"][0], self._sels[1]["dominant"][0]))
            extra = (f"\nTrait 1: {dom_val_str} > {rec_val_str}  ({trait_name})"
                     f"\nTrait 2: {dom2_val_str} > {rec2_val_str}  ({trait_name2})")

            # Update ratio UI for the chosen pair
            chosen_pair = frozenset({self._sels[0]["dominant"][0],
                                     self._sels[1]["dominant"][0]})
            all_pairs_ratios = res.get("law3_all_valid_pairs_ratios") or {}
            chosen_ratio = all_pairs_ratios.get(chosen_pair)
            if chosen_ratio:
                try:
                    app.law3_ratio_ui = chosen_ratio
                    app._update_law_status_label()
                except Exception:
                    pass

        else:
            extra = f"\nTrait: {dom_val_str} > {rec_val_str}  ({trait_name})"

        self._show_result(True,
            f"{law_name} confirmed!{extra}")


    # ── result popup ──────────────────────────────────────────────────────────

    # ── value normaliser (wizard uses "short", plants store "dwarf") ─────────

    @staticmethod
    def _norm_val(v):
        """Normalise a trait value so wizard strings and TIE strings compare equal."""
        v = (v or "").strip().lower()
        return {"dwarf": "short", "swollen": "inflated"}.get(v, v)

    # ── result popup ──────────────────────────────────────────────────────────

    def _show_result(self, success, message, close_after=False):
        """Show a result banner between the title bar and the scrollable body."""
        # remove any previous result banner
        for w in self._page2.winfo_children():
            if getattr(w, "_is_result_panel", False):
                w.destroy()

        color  = "#1E4D2A" if success else "#4A1818"   # deep forest green / soft dark red
        border = "#3AB050" if success else "#D04040"   # vivid green / vivid red
        icon   = "✔" if success else "✖"
        fg     = "#FFFFFF"   # white text on both banners

        panel = tk.Frame(self._page2, bg=color,
                         highlightbackground=border,
                         highlightthickness=2,
                         padx=16, pady=10)
        panel._is_result_panel = True
        # pack between the title bar and the scrollable canvas frame
        panel.pack(fill="x", padx=0, pady=0,
                   before=self._p2_canvas_frame)

        tk.Label(panel, text=f"{icon}  {message}",
                 font=self.FONT_BOLD, bg=color, fg=fg,
                 wraplength=660, justify="left").pack(anchor="w", padx=4)

        # ── swap nav button on outcome ────────────────────────────────────
        try:
            if success:
                # Unlock button becomes a green Close button.
                # The player can read the confirmation banner at their own pace.
                self._p2_unlock_btn.configure(
                    text="✔  Close",
                    command=self.destroy,
                    bg="#3AB050",
                    fg="#FFFFFF",
                    activebackground="#2A8040",
                    activeforeground="#FFFFFF",
                    state="normal",
                )
            else:
                # Failure: offer a quick way back to re-select traits
                self._p2_unlock_btn.configure(
                    text="↺  Try Again",
                    command=self._go_back,
                    bg="#D04040",
                    fg="#FFFFFF",
                    activebackground="#A02020",
                    activeforeground="#FFFFFF",
                    state="normal",
                )
        except Exception:
            pass


