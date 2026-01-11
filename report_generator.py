from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Asynchronous Order Management: Documentation & Analysis', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 6, label, 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, text):
        self.set_font('Arial', '', 11)
        self.multi_cell(0, 6, text)
        self.ln()

    def bullet_point(self, text):
        self.set_font('Arial', '', 11)
        self.cell(5) # Indent
        self.cell(5, 6, chr(149), 0, 0) # Bullet char
        self.multi_cell(0, 6, text)
        self.ln(2)

pdf = PDF()
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)

# --- Meta Info ---
pdf.set_font('Arial', 'I', 10)
pdf.cell(0, 6, 'Date: January 11, 2026', 0, 1)
pdf.cell(0, 6, 'Topic: Resolving WebSocket Disconnections via Non-Blocking Architecture', 0, 1)
pdf.ln(10)

# --- Section 1 ---
pdf.chapter_title('1. The Core Problem')
pdf.chapter_body(
    "The previous implementation of the OrderBookManager was synchronous (blocking).\n\n"
    "When the bot decided to place or cancel an order, the main execution thread would pause completely, "
    "waiting for the HTTP request to the exchange to finish (which can take 100ms - 2000ms).\n\n"
    "Consequence: While the main thread was paused waiting for the API, it stopped processing WebSocket "
    "heartbeats (Pings). The exchange server assumed the client was dead and closed the connection."
)

# --- Section 2 ---
pdf.chapter_title('2. The Solution: "Fire and Forget" Architecture')
pdf.chapter_body(
    "We refactored place_orders, cancel_orders, and cancel_all_orders to be asynchronous. "
    "The main thread now triggers a background task and immediately returns to listening for market data.\n"
)

pdf.set_font('Arial', 'B', 11)
pdf.cell(0, 6, 'Key Technical Changes:', 0, 1)
pdf.ln(2)

pdf.bullet_point("Removed wait(): We removed all instances of wait(results) and time.sleep(). The bot never explicitly pauses execution anymore.")
pdf.bullet_point("Fixed Thread Submission: Fixed a bug where 'submit(func(arg))' was blocking the main thread. Changed to 'submit(func, arg)'.")
pdf.bullet_point("Added Callbacks: Attached 'add_done_callback' to background threads to handle errors and cleanup counters automatically.")
pdf.ln(2)

# --- Section 3 ---
pdf.chapter_title('3. Implementation Logic')

# Table Header
pdf.set_font('Arial', 'B', 10)
pdf.set_fill_color(230, 230, 230)
pdf.cell(40, 7, 'Method', 1, 0, 'C', 1)
pdf.cell(50, 7, 'Role', 1, 0, 'C', 1)
pdf.cell(90, 7, 'Critical Safety Mechanism', 1, 1, 'C', 1)

# Table Rows
pdf.set_font('Arial', '', 10)

# Row 1
y_start = pdf.get_y()
pdf.cell(40, 14, 'place_orders', 1, 0, 'L')
pdf.cell(50, 14, 'Places new orders', 1, 0, 'L')
pdf.multi_cell(90, 7, 'Uses finally block in callback to ensure counter is decremented.', 1)

# Row 2
pdf.cell(40, 14, 'cancel_orders', 1, 0, 'L')
pdf.cell(50, 14, 'Cancels specific orders', 1, 0, 'L')
pdf.multi_cell(90, 7, 'Adds IDs to tracking set immediately; Callback removes them on completion.', 1)

# Row 3
pdf.cell(40, 14, 'cancel_all_orders', 1, 0, 'L')
pdf.cell(50, 14, 'Nukes all open orders', 1, 0, 'L')
pdf.multi_cell(90, 7, 'Replaced dangerous "while True" loop with a single background task.', 1)
pdf.ln(5)

# --- Section 4 ---
pdf.chapter_title('4. The New "Traffic Light" Strategy')
pdf.chapter_body(
    "Because the code is asynchronous, the Strategy cannot assume an order is gone the moment 'cancel_orders' returns. "
    "We introduced a state-check pattern to prevent 'Insufficient Funds' errors."
)

pdf.set_font('Arial', 'B', 11)
pdf.cell(0, 6, 'The Flow Cycle:', 0, 1)
pdf.ln(2)

pdf.bullet_point("Tick 1: Strategy sees bad orders -> Calls cancel_orders. (Returns instantly).")
pdf.bullet_point("Tick 2: Strategy checks 'has_pending_cancels'. It sees True. It SKIPS this cycle (waiting for funds).")
pdf.bullet_point("Tick 3: Background thread finishes. 'has_pending_cancels' becomes False.")
pdf.bullet_point("Tick 4: Strategy sees funds are free -> Calls place_orders.")

# Output
pdf.output("Async_Order_Management_Doc.pdf")
print("PDF generated successfully: Async_Order_Management_Doc.pdf")