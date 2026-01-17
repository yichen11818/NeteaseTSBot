use std::io;
use tracing::{Event, Subscriber};
use tracing_subscriber::{
    fmt::{format::Writer, FmtContext, FormatEvent, FormatFields},
    registry::LookupSpan,
    EnvFilter,
};

/// TSBot 统一日志格式化器
pub struct TSBotFormatter;

impl<S, N> FormatEvent<S, N> for TSBotFormatter
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    N: for<'a> FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        ctx: &FmtContext<'_, S, N>,
        mut writer: Writer<'_>,
        event: &Event<'_>,
    ) -> std::fmt::Result {
        // 获取时间戳
        let now = chrono::Local::now();
        let timestamp = now.format("%Y-%m-%d %H:%M:%S");
        
        // 获取日志级别
        let level = event.metadata().level();
        
        // 写入统一格式: [时间] [级别] [组件] 消息
        write!(writer, "[{}] [{}] [voice] ", timestamp, level)?;
        
        // 写入消息内容
        ctx.field_format().format_fields(writer.by_ref(), event)?;
        
        writeln!(writer)
    }
}

/// 初始化统一日志配置
pub fn init_logger() {
    use tracing_subscriber::fmt;
    
    let log_level = std::env::var("TSBOT_LOG_LEVEL").unwrap_or_else(|_| "info".to_string());
    let log_level = log_level.trim().to_lowercase();
    let log_level = if log_level.is_empty() { "info".to_string() } else { log_level };
    
    fmt()
        .event_format(TSBotFormatter)
        .with_env_filter(EnvFilter::new(format!("voice_service={}", log_level)))
        .with_writer(io::stdout)
        .init();
}
