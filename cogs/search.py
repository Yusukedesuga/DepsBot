import discord
from discord.ext import commands
from discord import app_commands
from duckduckgo_search import DDGS
import google.generativeai as genai
import os

class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except: pass

    @app_commands.command(name="search", description="【現在使えないと思います】Webを検索してFF14の情報を探します")
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        try:
            results_text = ""
            with DDGS() as ddgs:
                results = list(ddgs.text(f"{query} FF14", region='jp-jp', max_results=3))
                for r in results:
                    results_text += f"Title: {r['title']}\nURL: {r['href']}\nSummary: {r['body']}\n---\n"

            if not results_text:
                await interaction.followup.send("ごめん、それっぽい情報が見つからなかった…", ephemeral=True)
                return

            prompt = f"""
            ユーザーの質問「{query}」に対し、以下の検索結果を元にFF14プレイヤー向けに要約してください。
            もし検索結果がFF14と全く無関係なら「FF14に関する情報はなさそうです」と答えてください。
            
            検索結果:
            {results_text}
            """
            response = self.model.generate_content(prompt)
            await interaction.followup.send(f"🔍 **「{query}」の検索結果**\n{response.text}", ephemeral=True)

        except Exception as e:
            print(e)
            await interaction.followup.send("検索エラーが発生しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Search(bot))