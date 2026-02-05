import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import json
import os
import shutil

# データファイルのパス
DATA_DIR = "data"
IMAGES_DIR = os.path.join(DATA_DIR, "images")
TEMP_DIR = os.path.join(DATA_DIR, "temp") # 一時保存用
DATA_FILE = os.path.join(DATA_DIR, "knowledge.json")

# ------------------------------------------------------------------
# コンテンツ追加時の確認ビュー
# ------------------------------------------------------------------
class AddContentConfirmView(View):
    def __init__(self, cog, name, text_content, temp_folder):
        super().__init__(timeout=180)
        self.cog = cog
        self.name = name
        self.text_content = text_content
        self.temp_folder = temp_folder

    @discord.ui.button(label="✅ これで保存する", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        final_dir = os.path.join(IMAGES_DIR, self.name)
        
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        
        has_images = False
        if self.temp_folder and os.path.exists(self.temp_folder):
            shutil.move(self.temp_folder, final_dir)
            has_images = True
        
        self.cog.data["contents"][self.name] = {
            "text": self.text_content,
            "has_images": has_images
        }
        self.cog.save_data()

        await interaction.response.edit_message(content=f"✅ **「{self.name}」** を保存しました！", view=None, attachments=[])

    @discord.ui.button(label="❌ やめる", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if self.temp_folder and os.path.exists(self.temp_folder):
            shutil.rmtree(self.temp_folder)
            
        await interaction.response.edit_message(content="❌ 登録をキャンセルしました。", view=None, attachments=[])

# ------------------------------------------------------------------
# 削除などの確認ビュー
# ------------------------------------------------------------------
class ConfirmActionView(View):
    def __init__(self, cog, action_type, name, content=None):
        super().__init__(timeout=60)
        self.cog = cog
        self.action_type = action_type 
        self.name = name
        self.content = content

    @discord.ui.button(label="はい (実行)", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        msg = ""
        # --- マクロ ---
        if self.action_type == "add_macro":
            self.cog.data["macros"][self.name] = self.content
            msg = f"✅ マクロ **「{self.name}」** を登録しました！"
        elif self.action_type == "del_macro":
            if self.name in self.cog.data["macros"]:
                del self.cog.data["macros"][self.name]
                msg = f"🗑️ マクロ **「{self.name}」** を削除しました。"
            else:
                msg = "❌ エラー: データなし"
        elif self.action_type == "update_macro":
            self.cog.data["macros"][self.name] = self.content
            msg = f"🔄 マクロ **「{self.name}」** を更新しました！"

        # --- 攻略ボード ---
        elif self.action_type == "add_strat":
            self.cog.data["strategies"][self.name] = self.content
            msg = f"✅ 攻略ボード **「{self.name}」** を登録しました！"
        elif self.action_type == "del_strat":
            if self.name in self.cog.data["strategies"]:
                del self.cog.data["strategies"][self.name]
                msg = f"🗑️ 攻略ボード **「{self.name}」** を削除しました。"
            else:
                msg = "❌ エラー: データなし"
        elif self.action_type == "update_strat":
            self.cog.data["strategies"][self.name] = self.content
            msg = f"🔄 攻略ボード **「{self.name}」** を更新しました！"
        
        # --- コンテンツ削除 ---
        elif self.action_type == "del_content":
            target_dir = os.path.join(IMAGES_DIR, self.name)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            
            if self.name in self.cog.data["contents"]:
                del self.cog.data["contents"][self.name]
                msg = f"🗑️ コンテンツ **「{self.name}」** を完全に削除しました。"
            else:
                msg = "❌ エラー: データが見つかりません。"

        self.cog.save_data()
        await interaction.response.edit_message(content=msg, view=None, embed=None, attachments=[])

    @discord.ui.button(label="いいえ (キャンセル)", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ 操作をキャンセルしました。", view=None, embed=None, attachments=[])

# ------------------------------------------------------------------
# 更新用モーダル
# ------------------------------------------------------------------
class UpdateModal(Modal):
    def __init__(self, cog, name, current_content, data_type):
        title_text = f"{name} の編集"
        super().__init__(title=title_text)
        self.cog = cog
        self.name = name
        self.data_type = data_type 

        self.input_item = TextInput(
            label="新しい内容",
            style=discord.TextStyle.paragraph if data_type == "macro" else discord.TextStyle.short,
            default=current_content,
            required=True,
            max_length=2000
        )
        self.add_item(self.input_item)

    async def on_submit(self, interaction: discord.Interaction):
        new_value = self.input_item.value
        if self.data_type == "macro":
            preview = self.cog.format_macro(new_value)
            action = "update_macro"
        else:
            preview = new_value
            action = "update_strat"
        msg = f"⚠️ **以下の内容で更新しますか？**\nコンテンツ名: `{self.name}`\n\n新しい内容:\n```text\n{preview}\n```"
        view = ConfirmActionView(self.cog, action, self.name, new_value)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

# ------------------------------------------------------------------
# メイン機能クラス
# ------------------------------------------------------------------
class Knowledge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = self.load_data()

    def load_data(self):
        for d in [DATA_DIR, IMAGES_DIR, TEMP_DIR]:
            if not os.path.exists(d): os.makedirs(d)

        if not os.path.exists(DATA_FILE):
            init_data = {"macros": {}, "strategies": {}, "contents": {}}
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(init_data, f)
            return init_data
        
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "contents" not in data: data["contents"] = {}
            return data

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def format_macro(self, content):
        if "\n" not in content and "/p " in content:
            return content.replace("/p ", "\n/p ").strip()
        return content

    # ===============================================================
    # マクロ機能
    # ===============================================================
    @app_commands.command(name="addmacro", description="新しくマクロを登録します")
    @app_commands.rename(name="コンテンツ名", content="マクロ内容")
    async def add_macro(self, interaction: discord.Interaction, name: str, content: str):
        preview_content = self.format_macro(content)
        msg = f"**以下の内容で登録しますか？**\nコンテンツ名: `{name}`\n\nプレビュー:\n```text\n{preview_content}\n```"
        view = ConfirmActionView(self, "add_macro", name, content)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @app_commands.command(name="deletemacro", description="登録されたマクロを削除します")
    @app_commands.rename(name="コンテンツ名")
    async def delete_macro(self, interaction: discord.Interaction, name: str):
        if name not in self.data["macros"]:
            await interaction.response.send_message(f"❌ 「{name}」なし", ephemeral=True)
            return
        content = self.format_macro(self.data["macros"][name])
        msg = f"⚠️ **本当に削除しますか？**\nコンテンツ名: `{name}`\n\n中身:\n```text\n{content}\n```"
        view = ConfirmActionView(self, "del_macro", name)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @app_commands.command(name="changemacro", description="登録されたマクロを編集します")
    @app_commands.rename(name="コンテンツ名")
    async def change_macro(self, interaction: discord.Interaction, name: str):
        if name not in self.data["macros"]:
            await interaction.response.send_message(f"❌ 「{name}」なし", ephemeral=True)
            return
        await interaction.response.send_modal(UpdateModal(self, name, self.data["macros"][name], "macro"))

    @app_commands.command(name="viewmacro", description="登録されたマクロを表示します")
    @app_commands.rename(name="コンテンツ名")
    async def view_macro(self, interaction: discord.Interaction, name: str):
        content = self.data["macros"].get(name, "❌ なし")
        await interaction.response.send_message(f"**{name}**:\n```text\n{self.format_macro(content)}\n```", ephemeral=True)

    @delete_macro.autocomplete("name")
    @view_macro.autocomplete("name")
    @change_macro.autocomplete("name")
    async def macro_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=k, value=k) for k in self.data["macros"].keys() if current.lower() in k.lower()][:25]

    # ===============================================================
    # 攻略ボード機能
    # ===============================================================
    @app_commands.command(name="addstrategyboard", description="新しくストラテジーボードのコードを登録します")
    @app_commands.rename(name="コンテンツ名", code="コード")
    async def add_strat(self, interaction: discord.Interaction, name: str, code: str):
        msg = f"**以下の内容で登録しますか？**\nコンテンツ名: `{name}`\n\nプレビュー:\n```{code}```"
        view = ConfirmActionView(self, "add_strat", name, code)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @app_commands.command(name="deletestrategyboard", description="登録されたストラテジーボードのコードを削除します")
    @app_commands.rename(name="コンテンツ名")
    async def delete_strat(self, interaction: discord.Interaction, name: str):
        if name not in self.data["strategies"]:
            await interaction.response.send_message(f"❌ 「{name}」なし", ephemeral=True)
            return
        code = self.data["strategies"][name]
        msg = f"⚠️ **本当に削除しますか？**\nコンテンツ名: `{name}`\n\n中身:\n```{code}```"
        view = ConfirmActionView(self, "del_strat", name)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @app_commands.command(name="changestrategyboard", description="登録されたストラテジーボードのコードを編集します")
    @app_commands.rename(name="コンテンツ名")
    async def change_strat(self, interaction: discord.Interaction, name: str):
        if name not in self.data["strategies"]:
            await interaction.response.send_message(f"❌ 「{name}」なし", ephemeral=True)
            return
        await interaction.response.send_modal(UpdateModal(self, name, self.data["strategies"][name], "strat"))

    @app_commands.command(name="viewstrategyboard", description="登録されたストラテジーボードのコードを表示します")
    @app_commands.rename(name="コンテンツ名")
    async def view_strat(self, interaction: discord.Interaction, name: str):
        code = self.data["strategies"].get(name, "❌ なし")
        await interaction.response.send_message(f"**{name}**:\n```{code}```", ephemeral=True)

    @delete_strat.autocomplete("name")
    @view_strat.autocomplete("name")
    @change_strat.autocomplete("name")
    async def strat_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=k, value=k) for k in self.data["strategies"].keys() if current.lower() in k.lower()][:25]

    # ===============================================================
    # コンテンツ機能 (画像・メモ)
    # ===============================================================

    # 1. 登録
    @app_commands.command(name="addcontent", description="画像(最大10枚)やメモを登録します")
    @app_commands.rename(
        name="コンテンツ名", 
        memo1="メモ1", memo2="メモ2", memo3="メモ3",
        image1="画像1", image2="画像2", image3="画像3", image4="画像4", image5="画像5",
        image6="画像6", image7="画像7", image8="画像8", image9="画像9", image10="画像10"
    )
    async def add_content(
        self, interaction: discord.Interaction, name: str,
        memo1: str = None, memo2: str = None, memo3: str = None,
        image1: discord.Attachment = None, image2: discord.Attachment = None, image3: discord.Attachment = None,
        image4: discord.Attachment = None, image5: discord.Attachment = None, image6: discord.Attachment = None,
        image7: discord.Attachment = None, image8: discord.Attachment = None, image9: discord.Attachment = None, image10: discord.Attachment = None
    ):
        if name in self.data["contents"]:
            await interaction.response.send_message(f"⚠️ **「{name}」** は既に存在します。\n`/deletecontent` で削除してからやり直してください。", ephemeral=True)
            return

        # リスト化
        images = [i for i in [image1, image2, image3, image4, image5, image6, image7, image8, image9, image10] if i is not None]
        memos = [m for m in [memo1, memo2, memo3] if m is not None]

        if not images and not memos:
            await interaction.response.send_message("❌ 画像かメモのどちらかは入力してください！", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)

        combined_text = ""
        for i, m in enumerate(memos, 1):
            combined_text += f"📝 **メモ{i}**:\n{m}\n\n"
        combined_text = combined_text.strip()

        # 一時保存
        temp_save_dir = os.path.join(TEMP_DIR, f"{name}_{interaction.id}")
        saved_files = []
        if images:
            if not os.path.exists(temp_save_dir): os.makedirs(temp_save_dir)
            for i, attachment in enumerate(images, 1):
                ext = os.path.splitext(attachment.filename)[1]
                new_filename = f"{i:02d}_{attachment.filename}"
                file_path = os.path.join(temp_save_dir, new_filename)
                await attachment.save(file_path)
                saved_files.append(discord.File(file_path))

        preview_text = f"⚠️ **以下の内容で登録しますか？**\n\n📂 **{name}**\n{combined_text}"
        view = AddContentConfirmView(self, name, combined_text, temp_save_dir if images else None)
        
        if not saved_files:
            await interaction.followup.send(preview_text, view=view, ephemeral=True)
        else:
            await interaction.followup.send(preview_text, files=saved_files, view=view, ephemeral=True)

    # 2. 閲覧
    @app_commands.command(name="viewcontent", description="登録したコンテンツを表示します")
    @app_commands.rename(name="コンテンツ名")
    async def view_content(self, interaction: discord.Interaction, name: str):
        content_data = self.data["contents"].get(name)
        if not content_data:
            await interaction.response.send_message(f"❌ 「{name}」は見つかりません。", ephemeral=True)
            return
        
        if isinstance(content_data, dict) and "path" in content_data: 
             text_content = ""
             has_images = True
        else:
            text_content = content_data.get("text", "")
            has_images = content_data.get("has_images", False)

        response_text = f"📂 **{name}**\n\n{text_content}"
        
        files = []
        if has_images:
            target_dir = os.path.join(IMAGES_DIR, name)
            if os.path.exists(target_dir):
                sorted_files = sorted(os.listdir(target_dir))
                for filename in sorted_files:
                    file_path = os.path.join(target_dir, filename)
                    files.append(discord.File(file_path))

        if not files:
            await interaction.response.send_message(response_text, ephemeral=True)
        else:
            await interaction.response.send_message(response_text, files=files[:10], ephemeral=True)
            if len(files) > 10:
                await interaction.followup.send(files=files[10:], ephemeral=True)

    # 3. 削除
    @app_commands.command(name="deletecontent", description="登録されたコンテンツを削除します")
    @app_commands.rename(name="コンテンツ名")
    async def delete_content(self, interaction: discord.Interaction, name: str):
        if name not in self.data["contents"]:
            await interaction.response.send_message(f"❌ 「{name}」なし", ephemeral=True)
            return

        content_data = self.data["contents"][name]
        
        if isinstance(content_data, dict) and "path" in content_data: 
             text_content = ""
             has_images = True
        else:
            text_content = content_data.get("text", "")
            has_images = content_data.get("has_images", False)

        msg_text = f"⚠️ **本当に削除しますか？**\n\n📂 **{name}**\n{text_content}"
        
        files = []
        if has_images:
            target_dir = os.path.join(IMAGES_DIR, name)
            if os.path.exists(target_dir):
                sorted_files = sorted(os.listdir(target_dir))
                for filename in sorted_files:
                    file_path = os.path.join(target_dir, filename)
                    files.append(discord.File(file_path))

        view = ConfirmActionView(self, "del_content", name)

        if not files:
            await interaction.response.send_message(msg_text, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(msg_text, files=files[:10], view=view, ephemeral=True)

    # 4. 更新案内
    @app_commands.command(name="changecontent", description="コンテンツを更新します")
    @app_commands.rename(name="コンテンツ名")
    async def change_content(self, interaction: discord.Interaction, name: str):
        await interaction.response.send_message(
            f"🔄 コンテンツの更新は、一度 `/deletecontent` してから `/addcontent` し直してください！",
            ephemeral=True
        )

    # オートコンプリート
    @view_content.autocomplete("name")
    @delete_content.autocomplete("name")
    @change_content.autocomplete("name")
    async def content_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=k, value=k) for k in self.data["contents"].keys() if current.lower() in k.lower()][:25]

async def setup(bot):
    await bot.add_cog(Knowledge(bot))