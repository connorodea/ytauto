"""Interactive setup command — configure API keys and preferences."""

from __future__ import annotations

from pathlib import Path

import typer

from ytauto.cli.theme import console, header, step, success, warning


def setup() -> None:
    """Interactive setup wizard to configure API keys and defaults."""
    console.print()
    console.print(header(
        "ytauto Setup",
        "Let's configure your API keys and defaults.",
    ))

    env_dir = Path.home() / ".ytauto"
    env_dir.mkdir(parents=True, exist_ok=True)
    env_path = env_dir / ".env"

    # Load existing config if present
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                existing[key.strip()] = val.strip()

    entries: dict[str, str] = dict(existing)

    # Step 1: Anthropic
    step(1, "Anthropic API Key [dim](for script generation with Claude)[/dim]")
    console.print("  [dim]Get your key at: https://console.anthropic.com/settings/keys[/dim]")
    current = existing.get("YTAUTO_ANTHROPIC_API_KEY", "")
    hint = f" [dim](current: ...{current[-8:]})[/dim]" if current else ""
    val = typer.prompt(f"  API Key{hint}", default=current or "", show_default=False)
    if val:
        entries["YTAUTO_ANTHROPIC_API_KEY"] = val
        success("Anthropic API key saved")
    else:
        warning("Skipped Anthropic API key")

    # Step 2: OpenAI
    step(2, "OpenAI API Key [dim](for DALL-E image generation)[/dim]")
    console.print("  [dim]Get your key at: https://platform.openai.com/api-keys[/dim]")
    current = existing.get("YTAUTO_OPENAI_API_KEY", "")
    hint = f" [dim](current: ...{current[-8:]})[/dim]" if current else ""
    val = typer.prompt(f"  API Key{hint}", default=current or "", show_default=False)
    if val:
        entries["YTAUTO_OPENAI_API_KEY"] = val
        success("OpenAI API key saved")
    else:
        warning("Skipped OpenAI API key")

    # Step 3: Deepgram
    step(3, "Deepgram API Key [dim](for Aura TTS voiceover \u2014 recommended)[/dim]")
    console.print("  [dim]Get your key at: https://console.deepgram.com[/dim]")
    current = existing.get("YTAUTO_DEEPGRAM_API_KEY", "")
    hint = f" [dim](current: ...{current[-8:]})[/dim]" if current else ""
    val = typer.prompt(f"  API Key{hint}", default=current or "", show_default=False)
    if val:
        entries["YTAUTO_DEEPGRAM_API_KEY"] = val
        entries["YTAUTO_DEFAULT_TTS_PROVIDER"] = "deepgram"
        success("Deepgram API key saved (set as default TTS provider)")
    else:
        warning("Skipped Deepgram API key")

    # Step 4: ElevenLabs (optional)
    step(4, "ElevenLabs API Key [dim](optional \u2014 premium voices)[/dim]")
    skip = typer.confirm("  Skip?", default=True)
    if not skip:
        current = existing.get("YTAUTO_ELEVENLABS_API_KEY", "")
        val = typer.prompt("  API Key", default=current or "", show_default=False)
        if val:
            entries["YTAUTO_ELEVENLABS_API_KEY"] = val
            success("ElevenLabs API key saved")
    else:
        console.print("  [dim]Skipped ElevenLabs[/dim]")

    # Step 5: Default voice
    step(5, "Default TTS Voice")
    provider = entries.get("YTAUTO_DEFAULT_TTS_PROVIDER", "deepgram")
    current_voice = existing.get("YTAUTO_DEFAULT_TTS_VOICE", "aura-orion-en")

    if provider == "deepgram":
        console.print("  [dim]Deepgram Aura voices:[/dim]")
        dg_voices = [
            ("1", "aura-orion-en", "Orion \u2014 male, deep & authoritative"),
            ("2", "aura-arcas-en", "Arcas \u2014 male, warm & engaging"),
            ("3", "aura-perseus-en", "Perseus \u2014 male, confident & clear"),
            ("4", "aura-zeus-en", "Zeus \u2014 male, powerful & commanding"),
            ("5", "aura-asteria-en", "Asteria \u2014 female, warm & natural"),
            ("6", "aura-luna-en", "Luna \u2014 female, soft & soothing"),
            ("7", "aura-stella-en", "Stella \u2014 female, bright & clear"),
            ("8", "aura-athena-en", "Athena \u2014 female, professional"),
        ]
        for num, vid, desc in dg_voices:
            default = " [accent](default)[/accent]" if vid == "aura-orion-en" else ""
            console.print(f"    [accent]{num}.[/accent] {desc}{default}")
        console.print()
        choice = typer.prompt("  Voice [1-8]", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(dg_voices):
                entries["YTAUTO_DEFAULT_TTS_VOICE"] = dg_voices[idx][1]
                success(f"Voice set to {dg_voices[idx][2].split(' \u2014')[0]}")
            else:
                entries["YTAUTO_DEFAULT_TTS_VOICE"] = "aura-orion-en"
        except ValueError:
            # Allow direct voice ID input
            entries["YTAUTO_DEFAULT_TTS_VOICE"] = choice if choice.startswith("aura-") else "aura-orion-en"
    else:
        voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        console.print(f"  [dim]OpenAI voices: {', '.join(voices)}[/dim]")
        voice = typer.prompt("  Voice", default=current_voice)
        entries["YTAUTO_DEFAULT_TTS_VOICE"] = voice

    # Write .env file
    lines = ["# ytauto configuration", "# Generated by 'ytauto setup'", ""]
    for key, val in sorted(entries.items()):
        lines.append(f"{key}={val}")
    lines.append("")

    env_path.write_text("\n".join(lines), encoding="utf-8")

    console.print()
    success(f"Configuration saved to [path]{env_path}[/path]")
    console.print("  [dim]Run 'ytauto doctor' to verify your setup.[/dim]\n")
