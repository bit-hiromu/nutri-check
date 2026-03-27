# プロジェクト概要

外食チェーンの栄養成分（カロリー・タンパク質・脂質など）を一括で確認できるWebサービス。
チェーン店ごとの公式PDFから栄養データを取得・整備し、素早く検索・比較できる。

---

## ターゲットユーザー

- 外食時にカロリーやタンパク質をすぐ確認したい人
- ダイエット・筋トレ中で食事管理をしている人
- 忙しくてメニューをゆっくり調べる時間がない人

## サービスの強み

- 複数チェーンをまとめて横断検索できる
- メニューを複数選択して合計カロリーを計算できる
- 常時起動（スリープなし）で素早くアクセスできる

---

## 運営方針

- このプロジェクトは収益化を目指して運営する
- 運営コストは無料（無料ホスティング・無料サービスのみ使用）を維持する
- 有料サービスの導入は明示的な指示がある場合のみ検討する
- 収益化施策（広告、アフィリエイト等）の実装は指示に従い慎重に行う

## 収益化方針

- Google AdSense（独自ドメイン取得後に申請）
- アフィリエイト（サプリ・プロテイン・ダイエット食品など）
- 独自ドメイン取得を前提に設計する

---

## Mandatory Rules for Claude Code

- Do NOT modify any files unless explicitly instructed.
- Do NOT refactor existing code unless clearly requested.
- Prefer minimal, localized changes over large improvements.
- Stability and existing behavior are more important than code cleanliness.

### Change Proposal Requirement

Before making any code changes:

1. Explain what will be changed
2. Explain why it is necessary
3. Describe potential risks or side effects
4. Wait for explicit approval before proceeding.

### Security Rules

- Never request or output secrets, API keys, or credentials.
- Do not log or print personal data.
- Assume production-like constraints even in development.

### Cost Awareness

- Keep responses concise.
- Avoid repeating large code blocks unless necessary.
- Prefer explanation over full implementation when possible.

### Model Usage Policy

- Use the Default (recommended) model for all tasks.
- Do NOT switch to Opus unless explicitly instructed by the user.

---

## 言語設定

- 常に日本語で会話する
- コメントも日本語で記述する
- エラーメッセージの説明も日本語で行う

## コーディングルール

- すべてのコメントは日本語で記述
- 変数名・関数名は英語だが、その説明コメントは日本語
- TODOコメントも日本語で記載
