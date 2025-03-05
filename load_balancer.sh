#!/bin/bash
# Версия 2.0 - адаптировано для работы через Reverse SSH
# Настройка нагрузки через порт 4444 на VPS

### Конфигурация ###
LOGFILE="$HOME/load_balancer.log"          # Изменен путь для записи без прав root
MY_PC="wwssttl@5.180.82.44 -p 4444"       # Адрес через Reverse SSH-туннель
LOAD_THRESHOLD=90                          # Порог нагрузки CPU/RAM для активации
CHECK_INTERVAL=5                           # Интервал проверки (секунды)
HIGH_LOAD_DURATION_THRESHOLD=10            # Время устойчивой нагрузки для активации

### Системные параметры ###
SSH_OPTIONS="-o ConnectTimeout=5 -o StrictHostKeyChecking=no"
high_load_start=0

### Логирование ###
function log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" | tee -a "$LOGFILE"
}

function log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" | tee -a "$LOGFILE" >&2
}

### Проверка подключения к ПК ###
function is_pc_online() {
    ssh $SSH_OPTIONS $MY_PC "exit" &>/dev/null
    return $?
}

### Метрики системы ###
function get_cpu_usage() {
    awk '{u=$2+$4; t=$2+$4+$5; if (NR==1){u1=u; t1=t;} else print ($2+$4-u1) * 100 / (t-t1); }' \
    <(grep 'cpu ' /proc/stat) <(sleep 1; grep 'cpu ' /proc/stat) | tail -1 | awk '{print int($1)}'
}

function get_mem_usage() {
    free | awk '/Mem/{printf("%.0f"), $3/$2*100}' | tail -1
}

### Задачи ###
function perform_task() {
    log_info "Выполнение задачи на сервере ($(hostname))..."
    # Реальная нагрузка вместо sleep:
    openssl speed -multi $(nproc) >/dev/null 2>&1
}

function offload_task_to_pc() {
    log_info "Инициируем распределение нагрузки на ПК"
    
    # Команда для выполнения на ПК с нотификацией
    remote_command=$(cat <<'EOF'
export DISPLAY=:0
notify-send "Распределение нагрузки" "Сервер передал часть задачи на этот ПК"
stress-ng --cpu 0 -t 10s
EOF
)

    ssh $SSH_OPTIONS $MY_PC "$remote_command" >> "$LOGFILE" 2>&1 &
    pid=$!
    
    # Ожидание подтверждения запуска
    sleep 2
    if ps -p $pid >/dev/null; then
        log_info "Задача успешно запущена на ПК (PID: $pid)"
        return 0
    else
        log_error "Ошибка запуска задачи на ПК"
        return 1
    fi
}

### Основной цикл ###
while true; do
    cpu=$(get_cpu_usage)
    mem=$(get_mem_usage)
    
    log_info "Метрики: CPU=${cpu}% RAM=${mem}%"

    if [[ $cpu -ge $LOAD_THRESHOLD || $mem -ge $LOAD_THRESHOLD ]]; then
        if [[ $high_load_start -eq 0 ]]; then
            high_load_start=$(date +%s)
            log_info "Начало периода высокой нагрузки"
        else
            duration=$(( $(date +%s) - $high_load_start ))
            
            if [[ $duration -ge $HIGH_LOAD_DURATION_THRESHOLD ]]; then
                log_info "Устойчивая высокая нагрузка (${duration} сек) - активация распределения"
                
                # Параллельное выполнение
                offload_task_to_pc &
                pc_pid=$!
                perform_task &
                server_pid=$!
                
                # Ожидание завершения
                wait $pc_pid $server_pid
                high_load_start=0
                
                # Задержка перед следующей проверкой
                sleep $(( CHECK_INTERVAL * 2 ))
                continue
            fi
        fi
    else
        [[ $high_load_start -ne 0 ]] && log_info "Нагрузка нормализована"
