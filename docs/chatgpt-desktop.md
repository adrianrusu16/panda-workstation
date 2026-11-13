# ChatGPT Desktop on Panda Workstation

Use ChatGPT Desktop for graphical AI development and keep Codex CLI as the
terminal fallback. Check the existing Arch-style installation first:

```fish
fish bootstrap/panda-setup.fish --chatgpt-desktop
python -B bootstrap/dev/ai_tools.py codex-version
```

The Desktop check reads the local package inventory and checks
`/usr/bin/chatgpt` and `/usr/share/applications/chatgpt.desktop`.

## Optional manual installation

Use the [official OpenAI Linux installation guide](https://learn.chatgpt.com/docs/linux/linux-app#install-on-arch-linux).
OpenAI lists fully updated Arch Linux for the preview. CachyOS is outside its
published support list.

Review the downloaded installer and your host's upgrade plan before running
it. The installer adds the signed OpenAI pacman repository and performs a
full system upgrade, which can include the kernel. Run it only in a separate
attended maintenance window after explicitly approving that upgrade. Check
your Snapper recovery point and the host's boot and kernel policy first.
On Helios, defer installation until the proposed transaction has been
reviewed against the Helios safety contract. Standard Panda bootstrap
approval grants no approval for this installer.

After installation, rerun the inventory check, launch ChatGPT from the KDE
application menu, and sign in manually. Application sessions and account
setup are managed in ChatGPT.
