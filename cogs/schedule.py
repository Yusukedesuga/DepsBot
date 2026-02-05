import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput, Select
import datetime
import json
import os

DATA_FILE = "data/schedule.json"

# --- 設定 ---
DEFAULT_START_TIME = 21.0
DEFAULT_END_TIME = 24.0

TIME_OPTIONS = [
    (13.0, "13:00"), (13.5, "13:30"),
    (14.0, "14:00"), (14.5, "14:30"),
    (19.0, "19:00"), (19.5, "19:30"),
    (20.0, "20:00"), (20.5, "20:30"),
    (21.0, "21:00"), (21.5, "21:30"),
    (22.0, "22:00"), (22.5, "22:30"),
    (23.0, "23:00"), (23.5, "23:30"),
    (24.0, "24:00"), (24.5, "24:30"),
    (25.0, "25:00"), (25.5, "25:30"),
    (26.0, "26:00"),
]

# ------------------------------------------------------------------
# ユーティリティ
# ------------------------------------------------------------------
def format_float_time(t):
    h = int(t)
    m = int((t - h) * 60)
    return f"{h:02d}:{m:02d}"

def parse_date_str(date_str):
    try:
        date_str = date_str.replace("月", "/").replace("日", "")
        now = datetime.datetime.now()
        month, day = map(int, date_str.split("/"))
        year = now.year
        if month < now.month - 2: year += 1
        return datetime.datetime(year, month, day)
    except:
        return None

def parse_time_range(time_str):
    try:
        if "-" not in time_str: return None
        s_str, e_str = time_str.split("-")
        def tf(x):
            if ":" in x:
                h, m = map(int, x.split(":"))
                return h + m/60
            return float(x)
        return tf(s_str), tf(e_str)
    except:
        return None

# ------------------------------------------------------------------
# お知らせ編集モーダル (ホスト用)
# ------------------------------------------------------------------
class CommentEditModal(Modal, title="ホストからのお知らせ編集"):
    def __init__(self, cog, message_id, current_comment):
        super().__init__()
        self.cog = cog
        self.message_id = message_id

        self.comment_input = TextInput(
            label="お知らせ・メッセージ (空欄で削除)",
            style=discord.TextStyle.paragraph,
            placeholder="例: 基本は24時までですが、延長できる日はお願いします！",
            default=current_comment,
            required=False,
            max_length=500
        )
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_comment = self.comment_input.value
        if self.message_id in self.cog.data:
            self.cog.data[self.message_id]["host_comment"] = new_comment
            self.cog.save_data()
        
        await self.cog.update_panel(None, self.message_id)
        msg = "✅ お知らせを更新しました！" if new_comment else "🗑️ お知らせを削除しました。"
        await interaction.response.send_message(msg, ephemeral=True)

# ------------------------------------------------------------------
# 備考・メモのみ入力モーダル
# ------------------------------------------------------------------
class MemoOnlyModal(Modal, title="備考・メモの編集"):
    def __init__(self, cog, message_id, current_memo):
        super().__init__()
        self.cog = cog
        self.message_id = message_id

        self.memo_input = TextInput(
            label="備考・メモ",
            style=discord.TextStyle.paragraph, 
            placeholder="例:\n月曜は遅れます\n金曜は早く終わりたいです",
            default=current_memo,
            required=False,
            max_length=200
        )
        self.add_item(self.memo_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        
        if self.message_id not in self.cog.data:
            self.cog.data[self.message_id] = {"dates": [], "members": {}, "answers": {}, "memos": {}, "settings": {}}
        
        if "members" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["members"] = {}
        self.cog.data[self.message_id]["members"][user_id] = user_name

        new_memo = self.memo_input.value
        if "memos" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["memos"] = {}
        
        if new_memo:
            self.cog.data[self.message_id]["memos"][user_id] = new_memo
        elif user_id in self.cog.data[self.message_id]["memos"]:
            del self.cog.data[self.message_id]["memos"][user_id]

        self.cog.save_data()
        await self.cog.update_panel(None, self.message_id)
        await interaction.response.send_message("✅ メモを更新しました！", ephemeral=True)

# ------------------------------------------------------------------
# ポチポチ調整ビュー
# ------------------------------------------------------------------
class EasyAdjustView(View):
    def __init__(self, cog, message_id, user_id, user_name, target_dates, def_start, def_end):
        super().__init__(timeout=300)
        self.cog = cog
        self.message_id = message_id
        self.user_id = user_id
        self.user_name = user_name
        self.target_dates = target_dates
        self.def_start = def_start
        self.def_end = def_end
        
        self.selected_dates = []
        self.selected_start_offset = 0.0
        self.selected_end_offset = 0.0
        self.is_ng = False

        self.init_date_select()
        self.init_start_select()
        self.init_end_select()

    def init_date_select(self):
        options = []
        for d_str in self.target_dates:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            weekday = ["月","火","水","木","金","土","日"][dt.weekday()]
            label = f"{dt.month}/{dt.day} ({weekday})"
            options.append(discord.SelectOption(label=label, value=d_str))
        
        select = Select(
            placeholder="1. 変更・NGがある日だけ選んでください",
            min_values=1,
            max_values=len(options),
            options=options[:25],
            row=0
        )
        select.callback = self.on_date_select
        self.add_item(select)

    def init_start_select(self):
        s_str = format_float_time(self.def_start)
        options = [
            discord.SelectOption(label="❌ NG (不参加)", value="ng", description="この日は参加できません"),
            discord.SelectOption(label=f"⭕ 定時開始 ({s_str})", value="0.0"),
        ]
        
        offsets = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        for i in offsets:
            new_start = self.def_start + i
            if new_start < self.def_end:
                t_lbl = format_float_time(new_start)
                h_part = int(i)
                m_part = int((i - h_part) * 60)
                dur_str = ""
                if h_part > 0: dur_str += f"{h_part}時間"
                if m_part > 0: dur_str += f"{m_part}分"
                options.append(discord.SelectOption(label=f"⏰ {t_lbl} ({dur_str}遅れ)", value=str(i)))

        select = Select(
            placeholder="2. 開始時間 (またはNG)",
            options=options[:25],
            row=1
        )
        select.callback = self.on_start_select
        self.add_item(select)

    def init_end_select(self):
        e_str = format_float_time(self.def_end)
        options = [
            discord.SelectOption(label=f"⭕ 定時終了 ({e_str})", value="0.0"),
        ]
        
        offsets = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        for i in offsets:
            new_end = self.def_end - i
            if new_end > self.def_start:
                t_lbl = format_float_time(new_end)
                h_part = int(i)
                m_part = int((i - h_part) * 60)
                dur_str = ""
                if h_part > 0: dur_str += f"{h_part}時間"
                if m_part > 0: dur_str += f"{m_part}分"
                options.append(discord.SelectOption(label=f"🏃 {t_lbl} ({dur_str}早退)", value=str(i)))

        select = Select(
            placeholder="3. 終了時間",
            options=options[:25],
            row=2
        )
        select.callback = self.on_end_select
        self.add_item(select)

    async def on_date_select(self, interaction: discord.Interaction):
        self.selected_dates = interaction.data["values"]
        await interaction.response.defer()

    async def on_start_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "ng":
            self.is_ng = True
            self.selected_start_offset = 0.0
        else:
            self.is_ng = False
            self.selected_start_offset = float(val)
        await interaction.response.defer()

    async def on_end_select(self, interaction: discord.Interaction):
        self.selected_end_offset = float(interaction.data["values"][0])
        await interaction.response.defer()

    @discord.ui.button(label="適用する", style=discord.ButtonStyle.primary, row=3)
    async def apply_btn(self, interaction: discord.Interaction, button: Button):
        if not self.selected_dates:
            await interaction.response.send_message("❌ 日付を選択してください！", ephemeral=True)
            return

        if self.message_id not in self.cog.data:
            self.cog.data[self.message_id] = {"dates": [], "members": {}, "answers": {}, "memos": {}, "settings": {}}
        if "members" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["members"] = {}
        self.cog.data[self.message_id]["members"][self.user_id] = self.user_name
        if "answers" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["answers"] = {}
        if self.user_id not in self.cog.data[self.message_id]["answers"]:
            self.cog.data[self.message_id]["answers"][self.user_id] = {}

        for d in self.target_dates:
            if d not in self.cog.data[self.message_id]["answers"][self.user_id]:
                self.cog.data[self.message_id]["answers"][self.user_id][d] = (self.def_start, self.def_end)

        new_val = None
        if self.is_ng:
            new_val = None
        else:
            final_start = self.def_start + self.selected_start_offset
            final_end = self.def_end - self.selected_end_offset
            if final_start >= final_end:
                await interaction.response.send_message("❌ エラー: 開始時間が終了時間より後になっています。", ephemeral=True)
                return
            new_val = (final_start, final_end)

        count = 0
        for d in self.selected_dates:
            self.cog.data[self.message_id]["answers"][self.user_id][d] = new_val
            count += 1
        
        self.cog.save_data()
        await self.cog.update_panel(None, self.message_id)
        
        status_msg = "❌ NG"
        if new_val:
            s_str = format_float_time(new_val[0])
            e_str = format_float_time(new_val[1])
            status_msg = f"⏰ {s_str} 〜 {e_str}"

        await interaction.response.send_message(f"✅ {count}日分を **{status_msg}** に更新しました！\n続けて他の日も変更できます。", ephemeral=True)

    @discord.ui.button(label="終了", style=discord.ButtonStyle.secondary, row=3)
    async def close_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="✅ 編集を終了しました。", view=None)


# ------------------------------------------------------------------
# リスト一括編集モーダル (確認用)
# ------------------------------------------------------------------
class ConfirmScheduleView(View):
    def __init__(self, cog, message_id, user_id, user_name, new_answers, new_memo):
        super().__init__(timeout=60)
        self.cog = cog
        self.message_id = message_id
        self.user_id = user_id
        self.user_name = user_name
        self.new_answers = new_answers
        self.new_memo = new_memo

    @discord.ui.button(label="はい (確定)", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if self.message_id not in self.cog.data:
            self.cog.data[self.message_id] = {"dates": [], "members": {}, "answers": {}, "memos": {}, "settings": {}}

        if "members" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["members"] = {}
        self.cog.data[self.message_id]["members"][self.user_id] = self.user_name

        if self.new_memo is not None:
            if "memos" not in self.cog.data[self.message_id]:
                self.cog.data[self.message_id]["memos"] = {}
            
            if self.new_memo:
                self.cog.data[self.message_id]["memos"][self.user_id] = self.new_memo
            elif self.user_id in self.cog.data[self.message_id]["memos"]:
                del self.cog.data[self.message_id]["memos"][self.user_id]

        if "answers" not in self.cog.data[self.message_id]:
            self.cog.data[self.message_id]["answers"] = {}
        if self.user_id not in self.cog.data[self.message_id]["answers"]:
            self.cog.data[self.message_id]["answers"][self.user_id] = {}

        for d, val in self.new_answers.items():
            self.cog.data[self.message_id]["answers"][self.user_id][d] = val

        self.cog.save_data()
        await self.cog.update_panel(None, self.message_id)
        await interaction.response.edit_message(content="✅ **保存しました！**", view=None)

    @discord.ui.button(label="いいえ (修正)", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ **保存をキャンセルしました。**", view=None)


class LegacyBulkEditModal(Modal, title="リスト一括編集"):
    def __init__(self, cog, message_id, default_text, def_start, def_end):
        super().__init__()
        self.cog = cog
        self.message_id = message_id
        self.def_start = def_start
        self.def_end = def_end

        # ★ 45文字制限クリア
        self.schedule_input = TextInput(
            label="スケジュール一覧 (時間変更、NGは x (小文字) に)",
            style=discord.TextStyle.paragraph,
            default=default_text,
            required=True,
            max_length=2000
        )
        self.add_item(self.schedule_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        
        if self.message_id not in self.cog.data:
            await interaction.response.send_message("❌ データが見つかりません", ephemeral=True)
            return

        raw_text = self.schedule_input.value
        lines = raw_text.split("\n")
        target_dates_str = self.cog.data[self.message_id]["dates"]

        ng_words = ["x", "ng", "×", "無理", "だめ", "ダメ", "不可", "no"]
        ok_words = ["o", "ok", "○", "定時", "yes", "可"]
        error_lines = [] 
        temp_answers = {} 

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("※"): continue
            line_clean = line.replace(":", ":").replace("〜", "-")
            parts = line_clean.split()
            if len(parts) < 2: continue
            
            d_input, t_input = parts[0], parts[1]
            matched_date = None
            for td in target_dates_str:
                dt = datetime.datetime.strptime(td, "%Y-%m-%d")
                short_date = f"{dt.month}/{dt.day}"
                if d_input == short_date or d_input == str(dt.day):
                    matched_date = td
                    break
            
            if matched_date:
                lower_input = t_input.lower()
                if lower_input in ng_words:
                    temp_answers[matched_date] = None
                elif lower_input in ok_words:
                    temp_answers[matched_date] = (self.def_start, self.def_end)
                else:
                    val = parse_time_range(t_input)
                    if val:
                        temp_answers[matched_date] = val
                    else:
                        error_lines.append(f"⚠️「{line}」")

        if error_lines:
            await interaction.response.send_message(f"❌ エラー:\n" + "\n".join(error_lines), ephemeral=True)
            return

        final_answers = {}
        preview_lines = []
        for d_str in target_dates_str:
            if d_str in temp_answers:
                val = temp_answers[d_str]
            else:
                val = (self.def_start, self.def_end)
            
            final_answers[d_str] = val
            
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            d_disp = f"{dt.month}/{dt.day}"
            if val is None:
                preview_lines.append(f"• {d_disp}: ❌ NG")
            elif val != (self.def_start, self.def_end):
                preview_lines.append(f"• {d_disp}: ⚠️ {format_float_time(val[0])}-{format_float_time(val[1])}")
        
        msg = "**以下の内容で更新します。よろしいですか？**\n"
        if not preview_lines:
            msg += "（全日、定時参加で登録します）\n"
        else:
            msg += "※変更・NGの日程:\n" + "\n".join(preview_lines) + "\n"
        
        view = ConfirmScheduleView(self.cog, self.message_id, user_id, user_name, final_answers, None)
        await interaction.response.send_message(msg, view=view, ephemeral=True)


# ------------------------------------------------------------------
# 入力選択ビュー
# ------------------------------------------------------------------
class InputMenu(View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.message_id = message_id
        
        data = self.cog.data.get(message_id, {})
        settings = data.get("settings", {})
        self.def_start = settings.get("default_start", DEFAULT_START_TIME)
        self.def_end = settings.get("default_end", DEFAULT_END_TIME)
        self.start_str = int(self.def_start)
        self.end_str = int(self.def_end)

    @discord.ui.button(label="👆 ポチポチ調整モード", style=discord.ButtonStyle.success)
    async def easy_mode(self, interaction: discord.Interaction, button: Button):
        data = self.cog.data.get(self.message_id, {})
        target_dates = data.get("dates", [])
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        view = EasyAdjustView(self.cog, self.message_id, user_id, user_name, target_dates, self.def_start, self.def_end)
        await interaction.response.send_message("変更したい日付、開始時間、終了時間を選んで「適用」を押してください。\n**※ 選ばなかった日は、自動的に「定時(OK)」として扱われます**", view=view, ephemeral=True)

    @discord.ui.button(label=f"🚀 全日OK", style=discord.ButtonStyle.primary)
    async def all_ok(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name
        data = self.cog.data.get(self.message_id, {})
        target_dates = data.get("dates", [])
        
        final_answers = {}
        for d in target_dates:
            final_answers[d] = (self.def_start, self.def_end)
            
        msg = f"**{len(target_dates)}日間、すべて定時 ({self.start_str}-{self.end_str}) で登録します。**\nよろしいですか？"
        view = ConfirmScheduleView(self.cog, self.message_id, user_id, user_name, final_answers, None)
        await interaction.response.send_message(msg, view=view, ephemeral=True)

    @discord.ui.button(label="📝 備考・メモの追加", style=discord.ButtonStyle.secondary)
    async def edit_memo(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        data = self.cog.data.get(self.message_id, {})
        current_memo = data.get("memos", {}).get(user_id, "")
        await interaction.response.send_modal(MemoOnlyModal(self.cog, self.message_id, current_memo))

    @discord.ui.button(label="✏️ リスト編集 (一括)", style=discord.ButtonStyle.secondary)
    async def edit_list_legacy(self, interaction: discord.Interaction, button: Button):
        user_id = str(interaction.user.id)
        data = self.cog.data.get(self.message_id, {})
        target_dates = data.get("dates", [])
        current_answers = data.get("answers", {}).get(user_id, {})

        # ★修正: デフォルトの1行目説明を削除 (空リストからスタート)
        default_text_lines = []
        
        for d_str in target_dates:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
            short_date = f"{dt.month}/{dt.day}"
            
            if d_str in current_answers:
                val = current_answers[d_str]
            else:
                val = (self.def_start, self.def_end)

            if val is None:
                default_text_lines.append(f"{short_date} x")
            else:
                t_str = f"{format_float_time(val[0])}-{format_float_time(val[1])}"
                default_text_lines.append(f"{short_date} {t_str}")

        default_text = "\n".join(default_text_lines)
        
        await interaction.response.send_modal(
            LegacyBulkEditModal(self.cog, self.message_id, default_text, self.def_start, self.def_end)
        )


# ------------------------------------------------------------------
# メインビュー
# ------------------------------------------------------------------
class ScheduleView(View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.message_id = str(message_id)

    @discord.ui.button(label="📝 入力画面を開く", style=discord.ButtonStyle.primary, custom_id="sch_open", row=0)
    async def open_menu(self, interaction: discord.Interaction, button: Button):
        view = InputMenu(self.cog, self.message_id)
        await interaction.response.send_message("入力方法を選んでください：", view=view, ephemeral=True)

    @discord.ui.button(label="👁️ 全員の詳細確認", style=discord.ButtonStyle.success, custom_id="sch_details", row=0)
    async def view_details(self, interaction: discord.Interaction, button: Button):
        data = self.cog.data.get(self.message_id, {})
        target_dates = data.get("dates", [])
        members = data.get("members", {})
        answers = data.get("answers", {})
        settings = data.get("settings", {})
        
        def_s = settings.get("default_start", DEFAULT_START_TIME)
        def_e = settings.get("default_end", DEFAULT_END_TIME)
        default_duration = def_e - def_s
        
        if not members:
            await interaction.response.send_message("まだ回答者がいません。", ephemeral=True)
            return

        report = []
        for uid, uname in members.items():
            report.append(f"■ {uname}")
            user_ans = answers.get(uid, {})
            lines = []
            for d in target_dates:
                dt = datetime.datetime.strptime(d, "%Y-%m-%d")
                d_disp = f"{dt.month}/{dt.day}"
                
                if d in user_ans:
                    val = user_ans[d]
                    if val is None:
                        lines.append(f"  {d_disp}: ❌ NG")
                    else:
                        duration = val[1] - val[0]
                        if val == (def_s, def_e):
                            status_mark = "⭕"
                        elif duration < default_duration:
                            status_mark = "🔺"
                        else:
                            status_mark = "⭕"
                        time_str = f"{format_float_time(val[0])}-{format_float_time(val[1])}"
                        lines.append(f"  {d_disp}: {status_mark} {time_str}")
                else:
                     lines.append(f"  {d_disp}: ❓ 未回答")
            report.append("\n".join(lines))
            report.append("") 

        final_report = "\n".join(report)
        if len(final_report) > 1900:
            final_report = final_report[:1900] + "\n...(省略)"

        await interaction.response.send_message(f"```\n{final_report}\n```", ephemeral=True)


    @discord.ui.button(label="📢 お知らせ編集", style=discord.ButtonStyle.secondary, custom_id="sch_comment", row=1)
    async def edit_comment(self, interaction: discord.Interaction, button: Button):
        schedule_data = self.cog.data.get(self.message_id, {})
        author_id = schedule_data.get("author_id")

        if author_id and str(interaction.user.id) != str(author_id):
            await interaction.response.send_message("❌ お知らせを編集できるのは、このスケジュールを作成した人だけです。", ephemeral=True)
            return

        current_comment = schedule_data.get("host_comment", "")
        await interaction.response.send_modal(CommentEditModal(self.cog, self.message_id, current_comment))

    @discord.ui.button(label="🔄 更新", style=discord.ButtonStyle.secondary, custom_id="sch_refresh", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: Button):
        await self.cog.update_panel(interaction, self.message_id)
        await interaction.response.send_message("情報を更新しました。", ephemeral=True)

# ------------------------------------------------------------------
# Cog本体
# ------------------------------------------------------------------
class Schedule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = self.load_data()

    def load_data(self):
        if not os.path.exists("data"): os.makedirs("data")
        if not os.path.exists(DATA_FILE): return {}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    async def update_panel(self, interaction, message_id):
        if message_id not in self.data: return
        sch_data = self.data[message_id]
        target_dates_str = sch_data["dates"] 
        members = sch_data.get("members", {})
        answers = sch_data.get("answers", {})
        memos = sch_data.get("memos", {})
        host_comment = sch_data.get("host_comment", "") 
        
        settings = sch_data.get("settings", {})
        def_s = settings.get("default_start", DEFAULT_START_TIME)
        def_e = settings.get("default_end", DEFAULT_END_TIME)
        default_duration = def_e - def_s
        title_text = settings.get("title", "📅 固定活動スケジュール調整")

        embed = discord.Embed(title=title_text, color=discord.Color.blue())
        
        desc = f"**期間: {target_dates_str[0]} 〜 {target_dates_str[-1]}**\n"
        desc += f"今回の定時: **{format_float_time(def_s)} 〜 {format_float_time(def_e)}**\n"
        
        if host_comment:
            desc += f"\n📢 **お知らせ**\n```\n{host_comment}\n```"
        
        desc += "\n「📝 入力画面を開く」から回答してください。"
        embed.description = desc
        
        result_text = ""
        
        for date_str in target_dates_str:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            weekday = ["月","火","水","木","金","土","日"][dt.weekday()]
            display_date = f"**{dt.month}/{dt.day} ({weekday})**"

            day_availabilities = []
            missing_names = [] 
            
            for uid, uname in members.items():
                if uid in answers and date_str in answers[uid]:
                    val = answers[uid][date_str]
                    if val: 
                        day_availabilities.append(val)
                    else:
                        missing_names.append(uname) 
            
            total_member_count = len(members)
            if total_member_count == 0:
                result_text += f"⚪ {display_date}: 募集中\n"
                continue

            status_icon = "🔴"
            time_info = ""

            ok_count = len(day_availabilities)

            if ok_count < total_member_count:
                status_icon = "🔴"
                missing_str = ", ".join(missing_names)
                time_info = f"**{ok_count}/{total_member_count}人 (欠: {missing_str})**"
            else:
                common_start = max([t[0] for t in day_availabilities])
                common_end = min([t[1] for t in day_availabilities])
                
                if common_start < common_end:
                    duration = common_end - common_start
                    s_str = format_float_time(common_start)
                    e_str = format_float_time(common_end)
                    
                    if duration < default_duration:
                        status_icon = "🟡"
                        time_info = f"**{s_str} 〜 {e_str}** ({duration}h)"
                    else:
                        status_icon = "🟢"
                        time_info = f"**{s_str} 〜 {e_str}** ({duration}h)"
                else:
                    status_icon = "💔"
                    time_info = "時間合わず"

            result_text += f"{status_icon} {display_date}: {time_info}\n"

        legend_text = "\n**凡例:** 🟢=定時開催OK, 🟡=時間短縮で開催可, 🔴=欠席あり, 💔=時間合わず"
        final_result_text = "\n" + result_text + legend_text + "\n"
        
        embed.add_field(name="集計結果", value=final_result_text, inline=False)
        
        if members:
            m_list = []
            for uid, uname in members.items():
                user_ans = answers.get(uid, {})
                answered_days = len(user_ans)
                required_days = len(target_dates_str)
                
                if answered_days >= required_days:
                    check = "✅"
                else:
                    check = "⚠️"
                
                memo = memos.get(uid)
                
                display_str = f"**{uname}**{check}"
                if memo:
                    display_str += " 📝\n" 
                    memo_lines = memo.split("\n")
                    formatted_lines = []
                    for line in memo_lines:
                        formatted_lines.append(f"> {line}")
                    display_str += "\n".join(formatted_lines)
                
                m_list.append(display_str)
            
            embed.add_field(name="回答状況・備考", value="\n".join(m_list), inline=False)

        try:
            chn_id = sch_data.get("channel_id")
            if chn_id:
                chn = self.bot.get_channel(int(chn_id))
                if chn:
                    msg = await chn.fetch_message(int(message_id))
                    await msg.edit(embed=embed, view=ScheduleView(self, message_id))
        except Exception as e:
            print(f"Update Error: {e}")

    @app_commands.command(name="schedule", description="期間を指定して日程調整を作成します")
    @app_commands.describe(
        start_date="開始日 (例: 12/25)", 
        end_date="終了日 (例: 12/31)",
        default_time="今回の定時 (例: 22-25) ※省略時は21-24",
        title="タイトル (省略時は「固定活動スケジュール調整」になります)",
        message="ホストからのメッセージ (例: 遅れる日は早めに連絡してね)"
    )
    @app_commands.rename(start_date="開始日", end_date="終了日", default_time="定時", title="タイトル", message="メッセージ")
    async def create_schedule(self, interaction: discord.Interaction, start_date: str, end_date: str, default_time: str = None, title: str = None, message: str = None):
        s_dt = parse_date_str(start_date)
        e_dt = parse_date_str(end_date)
        
        if not s_dt or not e_dt:
            await interaction.response.send_message("❌ 日付エラー", ephemeral=True)
            return
        if s_dt > e_dt:
             await interaction.response.send_message("❌ 終了日が開始日より前です", ephemeral=True)
             return
        
        d_start = DEFAULT_START_TIME
        d_end = DEFAULT_END_TIME
        
        if default_time:
            parsed = parse_time_range(default_time)
            if parsed:
                d_start, d_end = parsed
            else:
                await interaction.response.send_message("❌ 時間の指定形式が正しくありません (例: 22-25)", ephemeral=True)
                return
        
        final_title = title if title else "📅 固定活動スケジュール調整"

        target_dates = []
        curr = s_dt
        while curr <= e_dt:
            target_dates.append(curr)
            curr += datetime.timedelta(days=1)
        
        if len(target_dates) > 25:
             await interaction.response.send_message("❌ 期間は最大25日までです", ephemeral=True)
             return

        target_dates_str = [d.strftime("%Y-%m-%d") for d in target_dates]

        embed = discord.Embed(title=final_title, description="作成中...", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        self.data[str(msg.id)] = {
            "channel_id": interaction.channel.id,
            "author_id": interaction.user.id,
            "dates": target_dates_str,
            "members": {}, "answers": {}, "memos": {},
            "host_comment": message if message else "",
            "settings": {
                "default_start": d_start,
                "default_end": d_end,
                "title": final_title
            }
        }
        self.save_data()
        await self.update_panel(None, str(msg.id))

async def setup(bot):
    await bot.add_cog(Schedule(bot))