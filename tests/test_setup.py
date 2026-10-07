from signalbrief.setup import main


def test_setup_preserves_existing_operator_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = 'GROQ_API_KEY=operator-test-key\nZAPIER_HOOK_URL=operator-test-hook\n'
    (tmp_path / '.env').write_text(original, encoding='utf-8')
    (tmp_path / '.env.example').write_text('GROQ_API_KEY=\nZAPIER_HOOK_URL=\n', encoding='utf-8')
    main()
    assert (tmp_path / '.env').read_text(encoding='utf-8') == original
