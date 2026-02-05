import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Botの設定
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# 起動時の処理
@bot.event
async def on_ready():
    print(f"🚀 新型Bot (ota_bot2) 起動: {bot.user}")
    print("------")

# Cogs読み込み
async def load_extensions():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f"✅ Loaded: {filename}")
            except Exception as e:
                print(f"⚠️ Failed to load {filename}: {e}")

# 同期コマンド (!sync)
@bot.command()
async def sync(ctx):
    print("同期を開始します...")
    await ctx.message.delete()
    synced = await bot.tree.sync()
    msg = await ctx.send(f"✅ {len(synced)} 個のコマンドを同期しました！")
    await asyncio.sleep(5)
    await msg.delete()

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == '__main__':
    if TOKEN:
        try:
            # Botを起動
            asyncio.run(main())
        except KeyboardInterrupt:
            # Ctrl + C を押した時の処理
            print("\n🛑 Botを停止しました。お疲れ様でした！")
        except Exception as e:
            # その他の予期せぬエラー
            print(f"❌ エラーが発生しました: {e}")
    else:
        print("❌ エラー: .envファイルが見つかりません！")