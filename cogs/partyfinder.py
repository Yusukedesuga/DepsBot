import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
import os
import datetime
import traceback
import copy

JP_DCS = {
    "Elemental": ["Aegis", "Atomos", "Carbuncle", "Garuda", "Gungnir", "Kujata", "Tonberry", "Typhon"],
    "Gaia": ["Alexander", "Bahamut", "Durandal", "Fenrir", "Ifrit", "Ridill", "Tiamat", "Ultima"],
    "Mana": ["Anima", "Asura", "Chocobo", "Hades", "Ixion", "Masamune", "Pandaemonium", "Titan"],
    "Meteor": ["Belias", "Mandragora", "Ramuh", "Shinryu", "Unicorn", "Valefor", "Yojimbo", "Zeromus"] 
}

# ------------------------------------------------------------------
# サーバー絵文字設定 & ユーティリティ
# ------------------------------------------------------------------
ROLE_ICONS = {
    "MT": "<:Warrior:1353785254866845759>",
    "ST": "<:Paladin:1353785243689156750>",
    "H1": "<:WhiteMage:1353785324119261225>",
    "H2": "<:Scholar:1353785313092305018>",
    "D1": "<:Monk:1353785428221886597>",
    "D2": "<:Dragoon:1353785394524586055>",
    "D3": "<:Bard:1353785358336397493>",
    "D4": "<:BlackMage:1353785370533167185>",
    "Tank": "<:TankRole:1428349057167921252>",
    "Healer": "<:HealerRole:1428349043020533761>",
    "DPS": "<:DPSRole:1428349025911963801>", 
    "DPS1": "<:DPSRole:1428349025911963801>",
    "DPS2": "<:DPSRole:1428349025911963801>",
    "Any": "<:Mentor:1427504379258212372>"
}

def get_emoji_safe(role_name):
    icon_str = ROLE_ICONS.get(role_name)
    if not icon_str:
        if "MT" in role_name or "ST" in role_name or "Tank" in role_name: icon_str = ROLE_ICONS.get("Tank")
        elif "H" in role_name or "Healer" in role_name: icon_str = ROLE_ICONS.get("Healer")
        elif "D" in role_name or "DPS" in role_name: icon_str = ROLE_ICONS.get("DPS")
    if not icon_str: return None
    if "<:" in icon_str and ">" in icon_str:
        return discord.PartialEmoji.from_str(icon_str)
    return icon_str

# ------------------------------------------------------------------
# 調整枠の能力選択ビュー
# ------------------------------------------------------------------
class AnyCapabilityView(View):
    def __init__(self, parent_view, user_name, party_type):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self.user_name = user_name
        self.selected_roles = set()
        
        if "FULL" in party_type:
            self.role_options = ["MT", "ST", "H1", "H2", "D1", "D2", "D3", "D4"]
        elif "LIGHT" in party_type:
            self.role_options = ["Tank", "Healer", "DPS"] 
        else: 
            self.role_options = ["Tank", "Healer", "DPS"]

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for role in self.role_options:
            is_selected = role in self.selected_roles
            style = discord.ButtonStyle.success if is_selected else discord.ButtonStyle.secondary
            emoji = get_emoji_safe(role)
            btn = Button(label=role, style=style, emoji=emoji)
            btn.callback = self.make_toggle_callback(role)
            self.add_item(btn)

        confirm_btn = Button(label="これで決定", style=discord.ButtonStyle.primary, row=2)
        confirm_btn.callback = self.confirm_callback
        self.add_item(confirm_btn)

    def make_toggle_callback(self, role):
        async def cb(interaction: discord.Interaction):
            if role in self.selected_roles:
                self.selected_roles.remove(role)
            else:
                self.selected_roles.add(role)
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        return cb

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_roles:
            await interaction.response.send_message("❌ 少なくとも1つはロールを選んでください！", ephemeral=True)
            return

        sorted_roles = [r for r in self.role_options if r in self.selected_roles]
        
        # 既存データを更新
        self.parent_view.any_members = [m for m in self.parent_view.any_members if m["name"] != self.user_name]
        self.parent_view.any_members.append({"name": self.user_name, "roles": sorted_roles})
        
        # 確定枠から削除
        for r, u in self.parent_view.members.items():
            if u == self.user_name: self.parent_view.members[r] = None
            
        # 再計算 (V3/V6 Logic)
        assigned_msg = self.parent_view.reset_and_recalc()
        
        self.parent_view.update_buttons()
        if self.parent_view.message:
            await self.parent_view.message.edit(embed=self.parent_view.make_embed(), view=self.parent_view)
        
        response_msg = "✅ 調整枠に参加しました！"
        if assigned_msg:
            response_msg += f"\n(💡 {assigned_msg})"
            
        await interaction.response.edit_message(content=response_msg, view=None)
        await self.parent_view.check_full_and_notify(interaction)

# ------------------------------------------------------------------
# ホスト用 Any選択ビュー
# ------------------------------------------------------------------
class HostAnySelectView(View):
    def __init__(self, data):
        super().__init__(timeout=180)
        self.data = data
        self.selected_roles = set()
        
        if "FULL" in data["type"]:
            self.role_options = ["MT", "ST", "H1", "H2", "D1", "D2", "D3", "D4"]
        elif "LIGHT" in data["type"]:
            self.role_options = ["Tank", "Healer", "DPS"]
        else:
            self.role_options = ["Tank", "Healer", "DPS"]
            
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for role in self.role_options:
            is_selected = role in self.selected_roles
            style = discord.ButtonStyle.success if is_selected else discord.ButtonStyle.secondary
            emoji = get_emoji_safe(role)
            btn = Button(label=role, style=style, emoji=emoji)
            btn.callback = self.make_toggle_callback(role)
            self.add_item(btn)

        confirm_btn = Button(label="次へ進む", style=discord.ButtonStyle.primary, row=2)
        confirm_btn.callback = self.confirm_callback
        self.add_item(confirm_btn)

    def make_toggle_callback(self, role):
        async def cb(interaction: discord.Interaction):
            if role in self.selected_roles:
                self.selected_roles.remove(role)
            else:
                self.selected_roles.add(role)
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        return cb

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_roles:
            await interaction.response.send_message("❌ 少なくとも1つはロールを選んでください！", ephemeral=True)
            return
        
        sorted_roles = [r for r in self.role_options if r in self.selected_roles]
        self.data["my_role_list"] = sorted_roles
        
        await interaction.response.edit_message(content="ありがとうございます。次は場所と日時を選んでください。", view=LocationTimeView(self.data))

# ------------------------------------------------------------------
# 募集パネル本体
# ------------------------------------------------------------------
class RecruitmentPanel(View):
    def __init__(self, data):
        super().__init__(timeout=None)
        self.data = data
        self.members = {} 
        self.any_members = [] 
        self.assigned_any_members = {} 
        self.notified_full = False
        self.message = None

        if "4" in data["type"] or "LIGHT" in data["type"]:
            self.max_members = 4
        else:
            self.max_members = 8

        if data["type"] == "LIGHT": roles = ["Tank", "Healer", "DPS1", "DPS2"]
        elif data["type"] == "FULL": roles = ["MT", "ST", "H1", "H2", "D1", "D2", "D3", "D4"]
        elif data["type"] == "FREE8": roles = [f"参加枠{i}" for i in range(1, 9)]
        else: roles = [f"参加枠{i}" for i in range(1, 5)]
        
        for r in roles: self.members[r] = None

        author = data["author"]
        my_role = data["my_role"]
        
        if my_role and my_role != "None":
            if my_role == "Any":
                role_list = data.get("my_role_list", [])
                if not role_list: role_list = ["All"]
                self.any_members.append({"name": author, "roles": role_list})
            elif my_role in self.members:
                self.members[my_role] = author
            elif "Tank" in my_role and "MT" in self.members:
                self.members["MT"] = author
            elif "参加枠" in my_role:
                 self.members["参加枠1"] = author

        self.reset_and_recalc()
        self.update_buttons()

    # ★★★ 自動割り当てロジック (V6ベース: 慎重派) ★★★
    def assign_member(self, name, target_slot, original_roles):
        self.members[target_slot] = name
        self.assigned_any_members[name] = original_roles
        self.any_members = [m for m in self.any_members if m["name"] != name]

    def reset_and_recalc(self):
        # 1. 自動割り当て解除
        for r, u in self.members.items():
            if u and u in self.assigned_any_members:
                self.members[r] = None
                original_roles = self.assigned_any_members[u]
                if not any(m["name"] == u for m in self.any_members):
                    self.any_members.append({"name": u, "roles": original_roles})
        self.assigned_any_members = {}

        # 2. ソルバー実行
        return self.run_smart_solver()

    def run_smart_solver(self):
        logs = []
        changed = True
        
        while changed:
            changed = False
            empty_slots = [r for r, u in self.members.items() if u is None]
            if not empty_slots or not self.any_members:
                break 

            current_anys = copy.deepcopy(self.any_members)
            
            for member in current_anys:
                name = member["name"]
                roles = member["roles"]
                
                # Role展開
                target_roles = []
                for r in roles:
                    if r == "DPS" and self.data["type"] == "LIGHT":
                        target_roles.extend(["DPS1", "DPS2"])
                    else:
                        target_roles.append(r)
                
                # 入れる席リスト
                valid_slots = [s for s in target_roles if s in empty_slots]
                
                # ★修正: 選択肢が「1つ」の時だけ確定させる
                # これにより、MT/STの両方が空いているなら、どちらにも確定しない。
                if len(valid_slots) == 1:
                    target_slot = valid_slots[0]
                    
                    original = next((m for m in self.any_members if m["name"] == name), None)
                    if original:
                        self.assign_member(name, target_slot, original["roles"])
                        logs.append(f"{name} → {target_slot}")
                        changed = True 
                        break # 再評価へ
        
        if logs:
            return "自動調整: " + ", ".join(logs)
        return None

    def get_current_count(self):
        seated_count = sum(1 for u in self.members.values() if u is not None)
        any_count = len(self.any_members)
        return seated_count + any_count

    def is_user_joined(self, user_name):
        in_seat = user_name in self.members.values()
        in_any = any(m["name"] == user_name for m in self.any_members)
        return in_seat or in_any

    async def check_full_and_notify(self, interaction: discord.Interaction):
        if self.notified_full: return
        if self.get_current_count() >= self.max_members:
            self.notified_full = True
            author_id = self.data.get("author_id")
            if author_id:
                try:
                    await interaction.channel.send(f"<@{author_id}> 🎉 **メンバーが満員になりました！**\n出発準備をお願いします！")
                except:
                    pass

    def update_buttons(self):
        self.clear_items()
        
        for role, user in self.members.items():
            style = discord.ButtonStyle.secondary
            disabled = False
            label = role
            if user:
                label = f"{role}: {user}"
                disabled = True
            else:
                if role in ["MT", "ST"] or "Tank" in role: style = discord.ButtonStyle.primary
                elif role in ["H1", "H2"] or "Healer" in role: style = discord.ButtonStyle.success
                elif "D" in role: style = discord.ButtonStyle.danger
            
            emoji = get_emoji_safe(role)
            btn = Button(label=label, style=style, custom_id=f"rec_{role}", disabled=disabled, emoji=emoji)
            btn.callback = self.make_role_callback(role)
            self.add_item(btn)
        
        any_label = "調整枠に入る"
        current_total = self.get_current_count()
        if current_total >= self.max_members: any_label = "調整枠 (満員)"
        
        any_btn = Button(label=any_label, style=discord.ButtonStyle.secondary, custom_id="rec_any", emoji=get_emoji_safe("Any"))
        any_btn.callback = self.join_any_callback
        self.add_item(any_btn)

        leave_btn = Button(label="参加を取り消す", style=discord.ButtonStyle.secondary, custom_id="rec_leave", emoji="👋", row=4)
        leave_btn.callback = self.leave_callback
        self.add_item(leave_btn)

        cancel = Button(label="募集を削除", style=discord.ButtonStyle.danger, custom_id="rec_delete", row=4)
        cancel.callback = self.cancel_callback
        self.add_item(cancel)

    def make_role_callback(self, role):
        async def cb(interaction: discord.Interaction):
            try:
                user_name = interaction.user.display_name
                
                if not self.is_user_joined(user_name):
                    if self.get_current_count() >= self.max_members:
                        await interaction.response.send_message(f"❌ **満員です！**", ephemeral=True)
                        return

                for r, u in self.members.items():
                    if u == user_name: self.members[r] = None
                self.any_members = [m for m in self.any_members if m["name"] != user_name]
                if user_name in self.assigned_any_members:
                    del self.assigned_any_members[user_name]

                self.members[role] = user_name
                
                # 再計算
                assigned_msg = self.reset_and_recalc()
                
                self.update_buttons()
                await interaction.response.edit_message(embed=self.make_embed(), view=self)
                
                if assigned_msg:
                    await interaction.followup.send(f"💡 {assigned_msg}", ephemeral=True)
                
                await self.check_full_and_notify(interaction)
                
            except Exception as e:
                print(f"❌ Role Error: {e}")
                traceback.print_exc()
        return cb

    async def join_any_callback(self, interaction: discord.Interaction):
        try:
            user_name = interaction.user.display_name
            if not self.is_user_joined(user_name):
                if self.get_current_count() >= self.max_members:
                    await interaction.response.send_message(f"❌ **満員です！**", ephemeral=True)
                    return
            
            view = AnyCapabilityView(self, user_name, self.data["type"])
            await interaction.response.send_message("担当できるロールを選択してください！", view=view, ephemeral=True)
            
        except Exception as e:
            print(f"❌ Any Error: {e}")
            traceback.print_exc()

    async def leave_callback(self, interaction: discord.Interaction):
        try:
            user_name = interaction.user.display_name
            removed = False
            for r, u in self.members.items():
                if u == user_name:
                    self.members[r] = None
                    removed = True
            original_len = len(self.any_members)
            self.any_members = [m for m in self.any_members if m["name"] != user_name]
            if len(self.any_members) < original_len:
                removed = True
            if user_name in self.assigned_any_members:
                del self.assigned_any_members[user_name]

            if removed:
                self.notified_full = False
                self.reset_and_recalc()
                self.update_buttons()
                await interaction.response.edit_message(embed=self.make_embed(), view=self)
                await interaction.followup.send("参加を取り消しました！", ephemeral=True)
            else:
                await interaction.response.send_message("あなたはまだ参加していません！", ephemeral=True)
        except Exception as e:
            print(f"❌ Leave Error: {e}")
            traceback.print_exc()

    async def cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.display_name == self.data["author"]:
            await interaction.response.edit_message(content="❌ **募集は削除されました。(スレッドを閉じます)**", embed=None, view=None)
            if isinstance(interaction.channel, discord.Thread):
                try:
                    await interaction.channel.edit(archived=True, locked=True)
                except:
                    pass
        else:
            await interaction.response.send_message("募集主しか削除できません！", ephemeral=True)

    def make_embed(self):
        total = self.get_current_count()
        status_text = f"現在の参加者: {total}/{self.max_members}人"
        embed = discord.Embed(title=f"⚔️ {self.data['content']}", color=discord.Color.orange())
        embed.set_author(name=status_text)
        
        info_text = (
            f"📍 **場所**: {self.data['dc']} / {self.data['world']}\n"
            f"⏰ **時間**: {self.data['time']}\n"
            f"📝 **メモ**: {self.data['comment']}\n"
            "━━━━━━━━━━━━━━━"
        )
        embed.description = info_text
        
        member_text = ""
        filled_roles = []
        for r, u in self.members.items():
            icon = get_emoji_safe(r) or "▫️"
            if u: 
                member_text += f"{icon} **{r}** : **`{u}`**\n"
                filled_roles.append(r)
            else: 
                member_text += f"{icon} {r} : 　\n"
        
        if self.any_members:
            member_text += "\n**👑 調整・補欠 (Any):**\n"
            for m in self.any_members:
                name = m["name"]
                roles = m["roles"]
                
                display_icons = ""
                
                valid_roles = []
                for r in roles:
                    if r == "All": 
                        display_icons = " (何でも)"
                        break
                    
                    if self.data["type"] == "LIGHT" and r == "DPS":
                        if "DPS1" not in filled_roles or "DPS2" not in filled_roles:
                            valid_roles.append(r)
                    elif r not in filled_roles:
                        valid_roles.append(r)
                
                if not display_icons:
                    if valid_roles:
                        for vr in valid_roles:
                            ic = get_emoji_safe(vr)
                            if ic: display_icons += str(ic) + " "
                            else: display_icons += vr + " "
                    else:
                        display_icons = " (空きなし)"

                member_text += f"┗ **{name}** {display_icons}\n"
                
        embed.add_field(name="👥 メンバー表", value=member_text, inline=False)
        embed.set_footer(text=f"主催: {self.data['author']}")
        return embed

# ------------------------------------------------------------------
# ウィザード (確認画面)
# ------------------------------------------------------------------
class ConfirmView(View):
    def __init__(self, data):
        super().__init__(timeout=180)
        self.data = data
    
    @discord.ui.button(label="投稿する！", style=discord.ButtonStyle.green)
    async def post(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        forum_id = os.getenv("RECRUIT_FORUM_ID")
        if not forum_id:
            await interaction.followup.send("❌ エラー: RECRUIT_FORUM_ID が設定されていません。", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(forum_id))
        if not channel:
            await interaction.followup.send(f"❌ エラー: チャンネルが見つかりません。", ephemeral=True)
            return

        try:
            final_view = RecruitmentPanel(self.data)
            thread = await channel.create_thread(
                name=f"【募集】{self.data['content']} @{self.data['time']}",
                content=f"📢 **{self.data['content']}** 行くよ！",
                embed=final_view.make_embed(),
                view=final_view
            )
            # メッセージオブジェクト保存 (Bug Fix)
            final_view.message = await thread.thread.fetch_message(thread.thread.last_message_id)

            await interaction.edit_original_response(content=f"✅ 募集を公開しました！\n{thread.thread.jump_url}", embed=None, view=None)
            
            try:
                chat_id = os.getenv("CHAT_CHANNEL_ID")
                role_id = os.getenv("ROLE_ID")
                if chat_id and role_id:
                    chat_channel = interaction.guild.get_channel(int(chat_id))
                    if chat_channel:
                        await chat_channel.send(f"<@&{role_id}> **{self.data['content']}** の募集が出たよ！\n参加はこちら -> {thread.thread.jump_url}")
            except:
                pass

        except Exception as e:
            await interaction.followup.send(f"❌ エラー: {e}", ephemeral=True)
            traceback.print_exc()

    @discord.ui.button(label="❌ やり直す", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ キャンセルしました。", embed=None, view=None)

# ------------------------------------------------------------------
# 以下、入力用ウィザード部品
# ------------------------------------------------------------------
class DetailModal(Modal, title="詳細コメント"):
    comment = TextInput(label="自由コメント", style=discord.TextStyle.paragraph, placeholder="例: 初見です！マクロはGame8で！", required=False)
    def __init__(self, data):
        super().__init__()
        self.data = data

    async def on_submit(self, interaction: discord.Interaction):
        self.data["comment"] = self.comment.value
        embed = discord.Embed(title="最終確認", description="公開しますか？", color=discord.Color.blue())
        embed.add_field(name="コンテンツ", value=self.data["content"])
        
        # ★修正: 自分のロール表示をアイコン付きに (ホストの確認画面)
        role_disp = self.data["my_role"]
        if role_disp == "Any":
            role_list = self.data.get("my_role_list", [])
            disp_parts = []
            for r in role_list:
                ic = get_emoji_safe(r)
                disp_parts.append(f"{r}{str(ic) if ic else ''}")
            role_disp = " / ".join(disp_parts) + " (調整)"
        
        embed.add_field(name="自分のロール", value=role_disp)
        embed.add_field(name="場所", value=f"{self.data['dc']} / {self.data['world']}")
        embed.add_field(name="時間", value=self.data["time"])
        embed.add_field(name="コメント", value=self.data["comment"])
        await interaction.response.edit_message(embed=embed, view=ConfirmView(self.data))

class LocationTimeView(View):
    def __init__(self, data):
        super().__init__(timeout=180)
        self.data = data
        self.temp_time = {"date": None, "hour": None, "minute": None}
        self.selections = {"dc": None, "world": None}
        self.init_dc_select()
        self.world_select = Select(placeholder="🔒 先にDCを選んでね", options=[discord.SelectOption(label="waiting...", value="dummy")], disabled=True, row=1)
        self.add_item(self.world_select)
        self.init_date_select()
        self.init_hour_select()
        self.init_minute_select()

    def init_dc_select(self):
        options = [discord.SelectOption(label=dc) for dc in JP_DCS.keys()]
        placeholder = f"🌐 {self.selections['dc']}" if self.selections['dc'] else "🌐 DCを選択"
        self.dc_select = Select(placeholder=placeholder, options=options, row=0)
        self.dc_select.callback = self.on_dc_select
        self.add_item(self.dc_select)

    def init_date_select(self):
        today = datetime.date.today()
        dates = []
        weekdays = ['月','火','水','木','金','土','日']
        for i in range(14):
            d = today + datetime.timedelta(days=i)
            label = f"{d.month}/{d.day} ({weekdays[d.weekday()]})"
            if i == 0: label += " [今日]"
            if i == 1: label += " [明日]"
            dates.append(discord.SelectOption(label=label, value=f"{d.year}/{d.month}/{d.day}"))
        placeholder = f"📅 {self.temp_time['date']}" if self.temp_time['date'] else "📅 日付を選択"
        self.date_select = Select(placeholder=placeholder, options=dates, row=2)
        self.date_select.callback = self.on_date_select
        self.add_item(self.date_select)

    def init_hour_select(self):
        hours = [discord.SelectOption(label=f"{h:02d}時", value=f"{h:02d}") for h in range(24)]
        placeholder = f"🕒 {self.temp_time['hour']}時" if self.temp_time['hour'] else "🕒 何時？"
        self.hour_select = Select(placeholder=placeholder, options=hours, row=3)
        self.hour_select.callback = self.on_hour_select
        self.add_item(self.hour_select)

    def init_minute_select(self):
        minutes = [discord.SelectOption(label=f"{m:02d}分", value=f"{m:02d}") for m in [0, 15, 30, 45]]
        placeholder = f"⏱ {self.temp_time['minute']}分" if self.temp_time['minute'] else "⏱ 何分？"
        self.minute_select = Select(placeholder=placeholder, options=minutes, row=4)
        self.minute_select.callback = self.on_minute_select
        self.add_item(self.minute_select)

    async def on_dc_select(self, interaction: discord.Interaction):
        selected_dc = self.dc_select.values[0]
        self.data["dc"] = selected_dc
        self.selections["dc"] = selected_dc
        self.remove_item(self.world_select)
        options = [discord.SelectOption(label=w) for w in JP_DCS[selected_dc]]
        self.world_select = Select(placeholder="🌍 Worldを選択", options=options, row=1)
        self.world_select.callback = self.on_world_select
        self.add_item(self.world_select)
        self.remove_item(self.dc_select)
        self.init_dc_select()
        await interaction.response.edit_message(view=self)

    async def on_world_select(self, interaction: discord.Interaction):
        self.data["world"] = self.world_select.values[0]
        self.selections["world"] = self.data["world"]
        self.world_select.placeholder = f"🌍 {self.data['world']}"
        await self.check_and_submit(interaction)

    async def on_date_select(self, interaction: discord.Interaction):
        self.temp_time["date"] = self.date_select.values[0]
        self.remove_item(self.date_select)
        self.init_date_select()
        await self.check_and_submit(interaction)

    async def on_hour_select(self, interaction: discord.Interaction):
        self.temp_time["hour"] = self.hour_select.values[0]
        self.remove_item(self.hour_select)
        self.init_hour_select()
        await self.check_and_submit(interaction)

    async def on_minute_select(self, interaction: discord.Interaction):
        self.temp_time["minute"] = self.minute_select.values[0]
        self.remove_item(self.minute_select)
        self.init_minute_select()
        await self.check_and_submit(interaction)

    async def check_and_submit(self, interaction: discord.Interaction):
        if "dc" in self.data and "world" in self.data and all(self.temp_time.values()):
            self.data["time"] = f"{self.temp_time['date']} {self.temp_time['hour']}:{self.temp_time['minute']}"
            await interaction.response.send_modal(DetailModal(self.data))
        else:
            await interaction.response.edit_message(view=self)

class OwnerRoleSelectView(View):
    def __init__(self, data):
        super().__init__(timeout=180)
        self.data = data
        if data["type"] == "FULL": roles = ["MT", "ST", "H1", "H2", "D1", "D2", "D3", "D4"]
        else: roles = ["Tank", "Healer", "DPS1", "DPS2"]
            
        for role in roles:
            style = discord.ButtonStyle.secondary
            if "MT" in role or "ST" in role or "Tank" in role: style = discord.ButtonStyle.primary
            elif "H" in role or "Healer" in role: style = discord.ButtonStyle.success
            elif "D" in role or "DPS" in role: style = discord.ButtonStyle.danger
            
            emoji = get_emoji_safe(role)
            btn = Button(label=role, style=style, emoji=emoji)
            btn.callback = self.make_callback(role)
            self.add_item(btn)

        any_btn = Button(label="👑 調整 (Any)", style=discord.ButtonStyle.secondary, emoji=get_emoji_safe("Any"), row=2)
        any_btn.callback = self.make_callback("Any")
        self.add_item(any_btn)

    def make_callback(self, role):
        async def cb(interaction: discord.Interaction):
            self.data["my_role"] = role
            if role == "Any":
                await interaction.response.edit_message(content="調整枠ですね！\nあなたが担当できるロールを選んでください。", view=HostAnySelectView(self.data))
            else:
                msg = f"あなたは **{role}** ですね！"
                await interaction.response.edit_message(content=f"{msg}\n次は場所と日時を選んでください。", view=LocationTimeView(self.data))
        return cb

class TypeSelectView(View):
    def __init__(self, content_name, author_name, author_id):
        super().__init__(timeout=180)
        self.data = {"content": content_name, "author": author_name, "author_id": author_id, "type": None, "my_role": "None"}
    
    @discord.ui.select(placeholder="募集タイプ", options=[
        discord.SelectOption(label="FULL PARTY (ロール指定あり)", value="FULL", description="討滅戦やレイドに行くならこれ！"),
        discord.SelectOption(label="LIGHT PARTY (ロール指定あり)", value="LIGHT", description="IDやヴァリアントダンジョンに行くならこれ！"),
        discord.SelectOption(label="FULL PARTY (誰でも)", value="FREE8", description="SS撮影会でもするかい？"),
        discord.SelectOption(label="LIGHT PARTY (誰でも)", value="FREE4", description="FLに行く準備は出来たかな？ルレ募集もこれがおすすめ！"),
    ])
    async def on_type(self, interaction: discord.Interaction, select: Select):
        self.data["type"] = select.values[0]
        if "FREE" in self.data["type"]:
            self.data["my_role"] = "参加枠1"
            await interaction.response.edit_message(content="場所と日時を選んでください！", view=LocationTimeView(self.data))
        else:
            await interaction.response.edit_message(content="あなたのロールを選んでください！", view=OwnerRoleSelectView(self.data))

class PartyFinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="pfinder", description="募集を作成します（非公開で作成）")
    @app_commands.rename(content_name="コンテンツ名") 
    async def pfinder(self, interaction: discord.Interaction, content_name: str):
        await interaction.response.send_message(
            f"「{content_name}」の募集を作成します。\nまずはタイプを選んでください。", 
            view=TypeSelectView(content_name, interaction.user.display_name, interaction.user.id), 
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(PartyFinder(bot))