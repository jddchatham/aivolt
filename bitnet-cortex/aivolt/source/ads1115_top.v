module ads1115_top (
    input wire clk, inout wire i2c_sda, inout wire i2c_scl,
    output wire led, output wire uart_tx
);
    reg sda_low = 0, scl_low = 0;
    wire sda_in, scl_in;
    IOBUF sda_iobuf(.O(sda_in), .IO(i2c_sda), .I(1'b0), .OEN(~sda_low));
    IOBUF scl_iobuf(.O(scl_in), .IO(i2c_scl), .I(1'b0), .OEN(~scl_low));

    reg [6:0] divider = 0;
    wire tick = (divider == 7'd124); // 400 kHz state tick, ~100 kHz I2C
    always @(posedge clk) divider <= tick ? 0 : divider + 1'b1;

    localparam IDLE=0, START_A=1, START_B=2, START_C=3,
      TX_SETUP=4, TX_HIGH=5, TX_LOW=6, ACK_SETUP=7, ACK_HIGH=8,
      ACK_LOW=9, RX_SETUP=10, RX_HIGH=11, RX_LOW=12,
      MACK_SETUP=13, MACK_HIGH=14, MACK_LOW=15, STOP_A=16,
      STOP_B=17, STOP_C=18, WAIT_CONV=19, WAIT_RETRY=20;

    reg [4:0] state = IDLE;
    reg [1:0] phase = 0; // config write, pointer write, conversion read
    reg [2:0] byte_index = 0, bit_index = 7;
    reg [15:0] wait_ticks = 0;
    reg all_ack = 1, read_ok = 0, rx_byte_index = 0;
    reg [7:0] rx_shift = 0, rx_msb = 0;
    reg [15:0] uart_value = 0;
    reg [24:0] heartbeat = 0;
    wire signed [15:0] conversion_value = {rx_msb, rx_shift};

    reg [7:0] tx_byte;
    reg [2:0] last_tx_byte;
    always @* begin
        tx_byte = 8'h00;
        last_tx_byte = 0;
        case (phase)
          0: begin
            last_tx_byte = 3;
            case (byte_index)
              0: tx_byte = 8'h90; // address + write
              1: tx_byte = 8'h01; // configuration pointer
              2: tx_byte = 8'hC5; // AIN0-to-GND, +/-2.048 V
              3: tx_byte = 8'h83; // single-shot, 128 SPS
              default: tx_byte = 0;
            endcase
          end
          1: begin
            last_tx_byte = 1;
            tx_byte = (byte_index == 0) ? 8'h90 : 8'h00;
          end
          default: tx_byte = 8'h91; // address + read
        endcase
    end

    always @(posedge clk) begin
      heartbeat <= heartbeat + 1'b1;
      if (tick) case (state)
        IDLE: begin
          sda_low<=0; scl_low<=0; phase<=0; byte_index<=0; bit_index<=7;
          all_ack<=1; read_ok<=0; state<=START_A;
        end
        START_A: begin sda_low<=0; scl_low<=0; state<=START_B; end
        START_B: begin sda_low<=1; state<=START_C; end
        START_C: begin scl_low<=1; bit_index<=7; state<=TX_SETUP; end

        TX_SETUP: begin sda_low<=~tx_byte[bit_index]; state<=TX_HIGH; end
        TX_HIGH: begin scl_low<=0; state<=TX_LOW; end
        TX_LOW: begin
          scl_low<=1;
          if (bit_index==0) state<=ACK_SETUP;
          else begin bit_index<=bit_index-1'b1; state<=TX_SETUP; end
        end
        ACK_SETUP: begin sda_low<=0; state<=ACK_HIGH; end
        ACK_HIGH: begin
          scl_low<=0; if (sda_in) all_ack<=0; state<=ACK_LOW;
        end
        ACK_LOW: begin
          scl_low<=1;
          if (byte_index==last_tx_byte) begin
            if (phase==2) begin
              rx_byte_index<=0; bit_index<=7; state<=RX_SETUP;
            end else state<=STOP_A;
          end else begin
            byte_index<=byte_index+1'b1; bit_index<=7; state<=TX_SETUP;
          end
        end

        RX_SETUP: begin sda_low<=0; state<=RX_HIGH; end
        RX_HIGH: begin
          scl_low<=0; rx_shift[bit_index]<=sda_in; state<=RX_LOW;
        end
        RX_LOW: begin
          scl_low<=1;
          if (bit_index==0) state<=MACK_SETUP;
          else begin bit_index<=bit_index-1'b1; state<=RX_SETUP; end
        end
        MACK_SETUP: begin
          sda_low<=~rx_byte_index;
          if (!rx_byte_index) rx_msb<=rx_shift;
          state<=MACK_HIGH;
        end
        MACK_HIGH: begin scl_low<=0; state<=MACK_LOW; end
        MACK_LOW: begin
          scl_low<=1; sda_low<=0;
          if (rx_byte_index) state<=STOP_A;
          else begin rx_byte_index<=1; bit_index<=7; state<=RX_SETUP; end
        end

        STOP_A: begin sda_low<=1; state<=STOP_B; end
        STOP_B: begin scl_low<=0; state<=STOP_C; end
        STOP_C: begin
          sda_low<=0; wait_ticks<=0;
          if (phase==0) state<=WAIT_CONV;
          else if (phase==1) begin
            phase<=2; byte_index<=0; state<=START_A;
          end else begin
            uart_value <= conversion_value;
            read_ok <= all_ack && (conversion_value > -16'sd128) &&
                       (conversion_value < 16'sd128);
            state<=WAIT_RETRY;
          end
        end
        WAIT_CONV: begin // 10 ms at 400 kHz
          if (wait_ticks==3999) begin
            phase<=1; byte_index<=0; wait_ticks<=0; state<=START_A;
          end else wait_ticks<=wait_ticks+1'b1;
        end
        WAIT_RETRY: begin // repeat about every 100 ms
          if (wait_ticks==39999) state<=IDLE;
          else wait_ticks<=wait_ticks+1'b1;
        end
        default: state<=IDLE;
      endcase
    end

    // Blink only after an acknowledged conversion read near zero.
    assign led = read_ok ? heartbeat[24] : 1'b0;

    // 115200-baud UART: transmit the latest raw value as four hex digits.
    reg [9:0] uart_shift = 10'h3ff;
    reg [8:0] uart_divider = 0;
    reg [3:0] uart_bit = 0;
    reg uart_busy = 0;
    reg [2:0] uart_char = 0;
    reg [25:0] uart_pause = 0;
    reg [7:0] uart_data;

    function [7:0] hex_ascii;
      input [3:0] nibble;
      begin
        hex_ascii = (nibble < 10) ? (8'h30 + nibble) : (8'h41 + nibble - 10);
      end
    endfunction

    always @* begin
      case (uart_char)
        0: uart_data = hex_ascii(uart_value[15:12]);
        1: uart_data = hex_ascii(uart_value[11:8]);
        2: uart_data = hex_ascii(uart_value[7:4]);
        3: uart_data = hex_ascii(uart_value[3:0]);
        4: uart_data = 8'h0d;
        default: uart_data = 8'h0a;
      endcase
    end

    always @(posedge clk) begin
      if (uart_busy) begin
        if (uart_divider == 9'd433) begin
          uart_divider <= 0;
          if (uart_bit == 9) begin
            uart_busy <= 0;
            uart_bit <= 0;
          end else begin
            uart_shift <= {1'b1, uart_shift[9:1]};
            uart_bit <= uart_bit + 1'b1;
          end
        end else uart_divider <= uart_divider + 1'b1;
      end else if (uart_char < 6) begin
        uart_shift <= {1'b1, uart_data, 1'b0};
        uart_divider <= 0;
        uart_bit <= 0;
        uart_busy <= 1;
        uart_char <= uart_char + 1'b1;
      end else if (uart_pause == 26'd49999999) begin
        uart_pause <= 0;
        uart_char <= 0;
      end else uart_pause <= uart_pause + 1'b1;
    end

    assign uart_tx = uart_busy ? uart_shift[0] : 1'b1;
endmodule
