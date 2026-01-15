/**
 * 前端统一日志工具
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3
}

class TSBotLogger {
  private level: LogLevel = LogLevel.INFO;
  private component: string = 'web';

  constructor(component: string = 'web') {
    this.component = component;
    
    // 从环境变量或本地存储获取日志级别
    const envLevel = import.meta.env.VITE_LOG_LEVEL || localStorage.getItem('tsbot_log_level');
    if (envLevel) {
      this.level = this.parseLogLevel(envLevel);
    }
  }

  private parseLogLevel(level: string): LogLevel {
    switch (level.toUpperCase()) {
      case 'DEBUG': return LogLevel.DEBUG;
      case 'INFO': return LogLevel.INFO;
      case 'WARN': return LogLevel.WARN;
      case 'ERROR': return LogLevel.ERROR;
      default: return LogLevel.INFO;
    }
  }

  private formatMessage(level: string, message: string): string {
    const timestamp = new Date().toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
    
    return `[${timestamp}] [${level}] [${this.component}] ${message}`;
  }

  private shouldLog(level: LogLevel): boolean {
    return level >= this.level;
  }

  debug(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      console.debug(this.formatMessage('DEBUG', message), ...args);
    }
  }

  info(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.INFO)) {
      console.info(this.formatMessage('INFO', message), ...args);
    }
  }

  warn(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.WARN)) {
      console.warn(this.formatMessage('WARN', message), ...args);
    }
  }

  error(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      console.error(this.formatMessage('ERROR', message), ...args);
    }
  }

  setLevel(level: LogLevel): void {
    this.level = level;
    localStorage.setItem('tsbot_log_level', LogLevel[level]);
  }
}

// 导出全局 logger 实例
export const logger = new TSBotLogger();

// 导出工厂函数用于创建组件特定的 logger
export const createLogger = (component: string) => new TSBotLogger(component);
