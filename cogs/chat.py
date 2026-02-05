import discord
from discord.ext import commands
from discord import app_commands
import google.generativeai as genai
import os
from dotenv import load_dotenv

# .envを読み込む
load_dotenv()

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                print("⚠️ 警告: GEMINI_API_KEY が見つかりません！.envを確認してください。")
            else:
                genai.configure(api_key=api_key)
                # ★修正点: エラーが出ない安定版の 'gemini-pro' に変更しました
                self.model = genai.GenerativeModel('gemini-pro')
                self.sessions = {}
        except Exception as e:
            print(f"Gemini Init Error: {e}")

    @app_commands.command(name="chat", description="【現在使えないと思います】るーしーと内緒話をします（履歴を覚えます・他人には見えません）")
    async def chat(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        try:
            # セッション（会話の履歴）がなければ新しく作る
            if user_id not in self.sessions:
                self.sessions[user_id] = self.model.start_chat(history=[])
            
            chat_session = self.sessions[user_id]
            
            # メッセージを送信
            response = chat_session.send_message(message)
            
            reply_text = response.text
            # 文字数が多すぎたらカットする
            if len(reply_text) > 1900:
                reply_text = reply_text[:1900] + "..."

            await interaction.followup.send(f"**あなた:** {message}\n\n**るーしー:**\n{reply_text}", ephemeral=True)

        except Exception as e:
            # エラー内容をターミナルに表示
            print(f"❌ Chat Error (User: {interaction.user.name}): {e}")
            
            # エラーが起きたら履歴をリセットして、次は動くようにする
            self.sessions[user_id] = self.model.start_chat(history=[])
            
            # ユーザーへのメッセージ
            await interaction.followup.send(f"ごめん、ちょっとエラーが出ちゃったみたい。（モデルをgemini-proに変更して再試行してね）\nエラー内容: {e}", ephemeral=True)

    @app_commands.command(name="forget", description="【現在使えないと思います】会話の履歴をリセットします")
    async def forget(self, interaction: discord.Interaction):
        # 強制的に履歴を空にする
        if hasattr(self, 'model'):
             self.sessions[interaction.user.id] = self.model.start_chat(history=[])
        await interaction.response.send_message("記憶をリセットしたよ！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Chat(bot))