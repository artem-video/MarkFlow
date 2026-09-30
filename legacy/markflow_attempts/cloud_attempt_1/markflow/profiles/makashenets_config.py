"""
Machine-readable Style Profile for Макашенец.
Used by classify.py to tag timeline events with appropriate treatment.
"""

PROFILE = {
    "client": "makashenets",
    "channel": "YouTube / political satire",
    "core_theme": "politics_as_videogame",

    # ---------- BANNED ----------------------------------------------------
    "banned": {
        "sounds": [
            "robert_b_weide",
        ],
        "clips": [
            "goood_no_the_office",
            "ace_ventura_plunger",
        ],
        "memes": [
            "дверь мне запили",
            "пацаны вообще ребята",
        ],
        "music_genres": [
            "electronic",
            "synth",
            "edm",
            "trap_beat",
        ],
        "rules": [
            "no_same_technique_more_than_3_times",
            "no_jokes_on_real_victims",
            "no_fabricated_facts",
        ],
    },

    # ---------- APPROVED SOUNDS -------------------------------------------
    "approved_sounds": {
        "vine_boom":          {"use": "heavy_comic_hit",    "tiktok": True},
        "taco_bell":          {"use": "notification_bing",  "tiktok": True},
        "chill_guy":          {"use": "relaxed_pause",      "tiktok": True},
        "cartoon_transition": {"use": "whoosh_cut",         "tiktok": True},
        "spider_man":         {"use": "pointing_moment",    "tiktok": True},
        "fnaf_2":             {"use": "horror_reveal",      "tiktok": True},
        "torn_paper":         {"use": "bleep_replacement",  "tiktok": False},
        "coin_pickup":        {"use": "strategy_game_stat", "tiktok": False},
        "fart":               {"use": "impressive_numbers", "tiktok": False},
    },

    # ---------- TECHNIQUES ------------------------------------------------
    "techniques": {
        "speech_slowdown": {
            "trigger": "cliché_phrase OR obvious_stupidity",
            "effect": "slow_to_50pct + optional_reverb",
        },
        "shocked_animals_chroma": {
            "trigger": "long_interview_sync_over_30s",
            "effect": "meme_overlay_chromakey",
        },
        "demotivator": {
            "trigger": "contradictory_statement",
            "effect": "black_border + white_caption_below",
        },
        "low_quality_emotiguy": {
            "trigger": "ironic_moment",
            "effect": "boomer_yellow_emoji_overlay OR pixel_glitch",
        },
        "spongebob_butt": {
            "trigger": "impressive_numbers",
            "effect": "spongebob_butt_freeze + squeak_sfx",
        },
        "gross_up": {
            "trigger": "disgusting_expression",
            "effect": "extreme_zoom_in + cartoon_stinger",
        },
        "sigma_aura_edit": {
            "trigger": "character_thinks_they_are_cool",
            "effect": "slowed_reverb + skull_replaced_by_rooster_emoji",
        },
        "spherize_putin": {
            "trigger": "putin_says_obvious_nonsense",
            "effect": "premiere_spherize_on_face",
            "alias_names": ["Пыпа", "ЛадимВладимыч"],
        },
        "game_hud_plashka": {
            "trigger": "any_political_event_or_statistic",
            "effect": "game_ui_overlay + game_sfx",
            "examples": [
                "achievement_unlocked",
                "hp_bar",
                "inventory_slot",
                "quest_accepted",
                "stat_block",
                "strategy_map_icon",
            ],
        },
        "atypical_quote": {
            "trigger": "important_quote",
            "effect": "creative_layout NOT plain_article_screenshot",
        },
    },

    # ---------- MUSIC -----------------------------------------------------
    "music": {
        "preferred": ["bass_guitar", "live_drums", "acoustic_guitar", "orchestra"],
        "forbidden": ["electronic", "synth", "edm", "lo-fi_beats"],
        "reason": "gives cinematic quality to narration",
    },

    # ---------- RED ZONES (never touch) -----------------------------------
    "red_zones": [
        "real_victims_interviews",    # вдовы, инвалиды
        "unverified_statistics",      # нет источника — пометить «сверить»
        "technique_used_4_plus",      # 4й раз = тик
    ],

    # ---------- CLASSIFIER CATEGORIES ------------------------------------
    # Used by classify.py to tag each transcript segment
    "classify_categories": {
        "cliché": {
            "treatment": "speech_slowdown",
            "sfx": "vine_boom",
        },
        "absurd_statement": {
            "treatment": "shocked_animals_chroma OR demotivator",
            "sfx": "taco_bell",
        },
        "impressive_number": {
            "treatment": "spongebob_butt",
            "sfx": "fart",
        },
        "political_event": {
            "treatment": "game_hud_plashka",
            "sfx": "coin_pickup OR strategy_sfx",
        },
        "putin_moment": {
            "treatment": "spherize_putin",
            "sfx": "vine_boom",
        },
        "important_quote": {
            "treatment": "atypical_quote",
            "sfx": None,
        },
        "profanity": {
            "treatment": "bleep_partial",   # Х**НЯ не всё слово
            "sfx": "torn_paper",
        },
        "long_sync": {
            "treatment": "shocked_animals_chroma",
            "sfx": "cartoon_transition",
        },
        "scary_real": {
            "treatment": "none",            # RED ZONE
            "sfx": None,
        },
    },
}
