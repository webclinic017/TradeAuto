import time
import logging
import traceback
import pandas as pd
from datetime import datetime
import strategies.exitcodes as exitcodes
"""
   Description:
   Params:

   Done:
        1) stradle with adjustments
        2) exit on stoploss or target hit
        3) enter and exit based on time
        4) final trade report
   TODO:
        1) Continue trade which closed due to program exit

"""


class IntradayStradel():
      kite = None
      instrument = None
      inputs = None
      calls = []
      puts  = []
      positions = []
      exit_flag = None
      data = []
      columns = ["Type","Option",
                 "Entry Price","Entry Time","Security at Entry",
                 "Exit Price","Exit Time","Security at Exit"]
      RANGE_MULTIPLIER = 12

      def print_description(self):
          logging.info(self.inputs.strategy.description)

      def wait_till_time(self,entry_time):
          while True:
              if (datetime.now().time() >=
                      datetime.strptime(entry_time,'%H:%M').time()):
                  return
              time.sleep(60)

      def check_exit_time(self,exit_time):
          if (datetime.now().time() >=
                  datetime.strptime(exit_time,'%H:%M').time()):
              logging.info("Current time beyond stragtegy exit time")
              self.close_all_positions()
              self.exit_flag = exitcodes.EXIT_TIMETRIGGER
              return True
          else:
              return False

      def get_security_price(self,security):
          return self.kite.quote(security)[security]["last_price"]

      def get_near_options(self,security_price,gap):
          near_price=round(security_price/gap)*gap
          self.start_price = near_price
          near_ce=(f"{self.inputs.strategy.opt_name}"
                   f"{self.inputs.strategy.opt_year}"
                   f"{self.inputs.strategy.opt_month}"
                   f"{self.inputs.strategy.opt_day}"
                   f"{near_price}"
                   "CE")
          near_pe=(f"{self.inputs.strategy.opt_name}"
                   f"{self.inputs.strategy.opt_year}"
                   f"{self.inputs.strategy.opt_month}"
                   f"{self.inputs.strategy.opt_day}"
                   f"{near_price}"
                   "PE")
          return near_ce,near_pe

      def get_avg_price_of_order(order_id):
          orders = kite.orders()
          for order in orders:
              if order['order_id'] == order_id:
                 return order['average_price']

      def record_trade(self,option,price,trade_type):
          if option.endswith("CE"):
             opt_type = "CE"
             if trade_type ==  "Entry":
                self.calls.append(option)
             else:
                self.calls.remove(option)
          elif option.endswith("PE"):
             opt_type = "PE"
             self.puts.append(option)
             if trade_type ==  "Entry":
                self.calls.append(option)
             else:
                self.calls.remove(option)
          time_now = datetime.now()
          security,security_price = self.quote_security()
          if trade_type ==  "Entry":
             self.positions.append(option)
             self.odf = self.odf.append({"Type":opt_type,
                               "Option":option,
                               "Entry":price,
                               "Entry Time":time_now,
                               "Security at Entry": security_price},
                               ignore_index=True)
          else:
             self.positions.remove(option)
             self.odf.loc[self.odf.Option == option,
                 ["Exit","Exit Time","Security at Exit"]] = [price,time_now,security_price]
          logging.info(f"Data Frame:\n{self.odf}")
          logging.info(f"CALLS :\n{self.calls}")
          logging.info(f"PUTS :\n{self.puts}")
          logging.info(f"POSTIONS :\n{self.positions}")
 
           
      def trade_stradel(self):
          security = self.inputs.strategy.security
          security_price = self.get_security_price(security)
          security_option_gap = self.inputs.strategy.opt_gap
          call,put = self.get_near_options(security_price,security_option_gap)
          logging.info(f"Stradel start with {call} and {put}")
          self.sell_security(call)
          self.sell_security(put)
          self.level = 0
          return None

      def price_opt_pair(self,opt_chain,price,key):
          return dict({key:abs(price - opt_chain[key]["last_price"])})

      def get_security_near_price(self,price,opt_type):
          opt_list = []
          opt_dict = {}
          start = int(self.start_price - (self.RANGE_MULTIPLIER * self.inputs.strategy.opt_gap))
          end = int(self.start_price + (self.RANGE_MULTIPLIER * self.inputs.strategy.opt_gap))
          for val in range(start,end,self.inputs.strategy.opt_gap):
              opt_list.append(f"{self.inputs.strategy.opt_name}"
                             f"{self.inputs.strategy.opt_year}"
                             f"{self.inputs.strategy.opt_month}"
                             f"{self.inputs.strategy.opt_day}"
                             f"{val}{opt_type}")
          opt_chain = self.kite.quote(opt_list)
          logging.debug(opt_chain)
          opt_price_lst = [self.price_opt_pair(opt_chain,price,k) for k in opt_list]
          for item in opt_price_lst:
              opt_dict.update(item)
          return min(opt_dict,key=opt_dict.get)

      def quote_security(self):
          main_security = self.inputs.strategy.security
          main_security_price = self.get_security_price(main_security)
          logging.info(f"{main_security} is now at {main_security_price}")
          return main_security,main_security_price
          

      def sell_put(self,price):
          self.quote_security()
          security = self.get_security_near_price(price,"PE")
          self.sell_security(security)
          return None

      def sell_call(self,price):
          self.quote_security()
          security = self.get_security_near_price(price,"CE")
          self.sell_security(security)
          return None

      def sell_security(self,security):
          self.quote_security()
          price = 0
          if self.inputs.realtrade:
            try:
                order_id = kite.place_order(tradingsymbol=security,
                                exchange=kite.EXCHANGE_NFO,
                                transaction_type=kite.TRANSACTION_TYPE_SELL,
                                quantity=self.inputs.strategy.lotsize,
                                variety=kite.VARIETY_REGULAR,
                                order_type=kite.ORDER_TYPE_MARKET,
                                product=kite.PRODUCT_DAY)
                price = self.get_avg_price_of_order(order_id) 
                logging.info(f"Sold {security} at price {price}"
                             f" and quantity {self.inputs.strategy.lotsize}")
            except Exception as e:
                logging.info(f"Order placement failed: {e.message}")
          else:
            price = self.kite.quote(f"{security}")[security]["last_price"]
            logging.info(f"Sold {security} at price {price}")
          self.record_trade(security,price,"Entry")

      def buy_security(self,security):
          self.quote_security()
          price = 0 
          if self.inputs.realtrade:
            try:
                order_id = kite.place_order(tradingsymbol=security,
                                exchange=kite.EXCHANGE_NFO,
                                transaction_type=kite.TRANSACTION_TYPE_BUY,
                                quantity=self.inputs.strategy.lotsize,
                                variety=kite.VARIETY_REGULAR,
                                order_type=kite.ORDER_TYPE_MARKET,
                                product=kite.PRODUCT_DAY)
                price = self.get_avg_price_of_order(order_id) 
                logging.info(f"Bought {security} at price {price}"
                             f" and quantity {self.inputs.strategy.lotsize}")
            except Exception as e:
                logging.info(f"Order placement failed: {e.message}")
          else:
            price = self.kite.quote(f"{security}")[security]["last_price"]
            logging.info(f"Bought {security} at price {price}") 
          self.record_trade(security,price,"Exit")

      def check_and_add_options(self):
          call_price = 0
          put_price  = 0 
          for c in self.calls:
              call_price = call_price + self.kite.quote(f"{c}")[c]["last_price"]
              logging.debug(f"{c} is at price {call_price}")
          for p in self.puts:
              put_price = put_price + self.kite.quote(f"{p}")[p]["last_price"]
              logging.debug(f"{p} is at price {put_price}")
          if call_price/2 > put_price :
              #call is double to put.
              #adjust with put which is 1/4th price of call
              self.sell_put(call_price/4)
              self.level = self.level + 1
          if put_price/2 > call_price:
              #put is double to put.
              #adjust with call which is 1/4th price of put
              self.sell_call(put_price/4)
              self.level = self.level + 1

      def generate_report(self):
          if len(self.positions) == 0:
             return 
          share_PnL = self.odf["Entry"].sum() - self.odf["Exit"].sum()
          total_PnL = share_PnL * self.inputs.strategy.lotsize
          logging.info(odf)
          logging.info(f"Total Profit/Loss: {total_PnL}")

      def close_all_positions(self):
          for p in self.positions:
              self.buy_security(p)
          logging.info("Closed all positions")
          self.generate_report()

      def stop_loss_hit(self):
          total_current_val = 0 
          for p in self.positions:
             total_current_val = (total_current_val +
                                 self.kite.quote(f"{p}")[p]["last_price"])
          lossp = ((total_current_val - self.TOTAL_ENTRY_VAL) / 
                   self.TOTAL_ENTRY_VAL * 100)
          if lossp > self.inputs.strategy.stoploss:
             return True
          return False
          

      def check_stop_loss_exit(self):
          if self.TOTAL_ENTRY_VAL == 0:
               self.TOTAL_ENTRY_VAL = self.odf["Entry"].sum()
          if self.stop_loss_hit():
               self.close_all_positions()
               self.exit_flag = exitcodes.EXIT_STOPLOSS
          else:
               self.check_and_remove_options()

      def exit_put_with_low_price(self):
          p = self.puts[0]
          min_put = self.kite.quote(f"{p}")[p]["last_price"]
          for p in self.puts:
             price = self.kite.quote(f"{p}")[p]["last_price"]
             if price < min_price:
                  min_put = p
          self.buy_security(min_put)
          
 
      def exit_call_with_low_price(self):
          c = self.calls[0]
          min_call = self.kite.quote(f"{c}")[c]["last_price"]
          for c in self.calls:
             price = self.kite.quote(f"{c}")[c]["last_price"]
             if price < min_price:
                  min_call= c
          self.buy_security(min_call)
 

      def check_and_remove_options(self):
          call_price = 0
          put_price  = 0
          for c in self.calls:
              call_price = call_price + self.kite.quote(f"{c}")[c]["last_price"]
          for p in self.puts:
              put_price = put_price + self.kite.quote(f"{p}")[p]["last_price"]
          if call_price <= put_price and len(self.puts) > 1:
             self.exit_put_with_low_price()
          if call_price >= put_price and len(self.calls) > 1:
             self.exit_call_with_low_price()

      def check_target_hit_exit(self):
          total_entry_val = self.odf["Entry"].sum()
          total_current_val = 0
          for p in self.positions:
             total_current_val = total_current_val + self.kite.quote(f"{p}")[p]["last_price"]
          profitp = (total_current_val - self.total_entry_val)/self.total_entry_val * 100
          if profitp > self.inputs.strategy.target:
             return True
          return False
          

      def check_and_adjust(self):
          self.check_target_hit_exit()
          self.check_exit_time(self.inputs.strategy.exit.time)
          if self.level < 2 :
              self.check_and_add_options()
          else:
              self.check_stop_loss_exit()

      def watch_adjust_or_exit(self):
          while True:
              if self.exit_flag :
                  exit(self.exit_flag)
              try:
                self.check_and_adjust()
              except Exception as e:
                logging.info(f"Exception occuredi{e}")
                logging.info(traceback.format_exc())
              time.sleep(5)

      def execute_strategy(self):
          if self.inputs.strategy.entry.type == "time":
              if self.check_exit_time(self.inputs.strategy.exit.time):
                 exit(exitcodes.EXIT_TIMETRIGGER)
              self.wait_till_time(self.inputs.strategy.entry.time)
          self.trade_stradel()
          self.watch_adjust_or_exit()

      def start_trade(self,kite,inputs):
          self.kite = kite
          self.inputs = inputs
          self.odf = pd.DataFrame(self.data,columns=self.columns)
          self.print_description()
          self.execute_strategy() 



