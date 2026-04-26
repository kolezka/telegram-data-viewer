# Troubleshooting

Common failure modes when running `tg-viewer` and how to resolve them.

<details>
<summary><b>Decryption fails with "file is not a database"</b></summary>

- Ensure `PRAGMA cipher_default_plaintext_header_size = 32` is set BEFORE the key
- Check that `.tempkeyEncrypted` exists in the backup directory

</details>

<details>
<summary><b>No keys found in keychain</b></summary>

- For App Store version: keys are in `.tempkeyEncrypted`, not keychain. Use `apps/tool/tg_appstore_decrypt.py`
- For Desktop version: check `key_data` file in tdata directory

</details>

<details>
<summary><b>Database locked</b></summary>

- Quit Telegram completely: `killall Telegram`

</details>

<details>
<summary><b>Custom passcode set</b></summary>

- Pass it as an argument: `(cd apps && python3 -m tool.tg_appstore_decrypt ../data --password "your_passcode")`

</details>
