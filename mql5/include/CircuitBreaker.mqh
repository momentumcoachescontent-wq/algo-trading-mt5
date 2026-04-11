//+------------------------------------------------------------------+
//|  CircuitBreaker.mqh                                              |
//|  Kill-switch automático por drawdown de cuenta.                  |
//|  Versión: 1.0  |  Fase: F2  |  Fecha: 2026-03-31               |
//+------------------------------------------------------------------+
//  WHY:  Un flash-crash o ejecución errónea puede liquidar la cuenta
//        antes de que el operador reaccione.  Este módulo detiene el
//        EA de forma irreversible en la sesión cuando el drawdown
//        supera InpKillDD.  Es la primera línea de defensa y NO debe
//        desactivarse durante el trading real.
//+------------------------------------------------------------------+
#ifndef __CIRCUITBREAKER_MQH__
#define __CIRCUITBREAKER_MQH__

class CCircuitBreaker
{
private:
   bool      m_triggered;
   datetime  m_triggerTime;
   double    m_initialBalance;
   double    m_killDDPct;

public:
   CCircuitBreaker()
   {
      m_triggered      = false;
      m_triggerTime    = 0;
      m_initialBalance = 0.0;
      m_killDDPct      = 5.0;
   }

   void Init(double killDDPct = 5.0)
   {
      m_triggered      = false;
      m_triggerTime    = 0;
      m_initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      m_killDDPct      = killDDPct;

      Print("CircuitBreaker inicializado.");
      PrintFormat("Kill DD >= %.2f%%", m_killDDPct);
      PrintFormat("Balance inicial = %.2f", m_initialBalance);
   }

   double GetInitialBalance() const
   {
      return m_initialBalance;
   }

   double CurrentDrawdown() const
   {
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);

      if(m_initialBalance <= 0.0)
         return 0.0;

      return ((m_initialBalance - equity) / m_initialBalance) * 100.0;
   }

   bool IsTriggered() const
   {
      return m_triggered;
   }

   datetime TriggerTime() const
   {
      return m_triggerTime;
   }

   bool IsOperational()
   {
      if(m_triggered)
         return false;

      double dd = CurrentDrawdown();
      if(dd >= m_killDDPct)
      {
         m_triggered   = true;
         m_triggerTime = TimeCurrent();
         PrintFormat("CIRCUIT BREAKER ACTIVADO | DD=%.2f%% | límite=%.2f%%", dd, m_killDDPct);
         return false;
      }

      return true;
   }

   void Reset()
   {
      m_triggered      = false;
      m_triggerTime    = 0;
      m_initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   }
};

#endif