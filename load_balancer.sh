#!/bin/bash
# Скрипт для распределения нагрузки между сервером и основным ПК с измерением длительности высокой нагрузки
# и расширенным логированием для отладки передачи задачи на основной ПК

# Настройки
LOGFILE="/var/log/load_balancer.log"
MY_PC="wwssttl@192.168.1.5"  # замените на адрес вашего ПК
LOAD_THRESHOLD=90
CHECK_INTERVAL=2  # интервал проверки в секундах
HIGH_LOAD_DURATION_THRESHOLD=5  # порог времени высокой нагрузки (в секундах)

# Переменная для хранения времени начала высокой нагрузки
high_load_start=0

# Функция логирования информационных сообщений
function log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" | tee -a "$LOGFILE"
}

# Функция логирования ошибок
function log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" | tee -a "$LOGFILE" >&2
}

# Функция проверки доступности ПК через SSH
function is_pc_online() {
    log_info "Проверка доступности ПК: $MY_PC"
    ssh -o ConnectTimeout=5 "$MY_PC" "echo online" &>/dev/null
    result=$?
    if [ $result -eq 0 ]; then
        log_info "ПК $MY_PC доступен."
    else
        log_error "ПК $MY_PC недоступен (код ошибки: $result)."
    fi
    return $result
}

# Функция для получения текущей загрузки CPU (в процентах)
function get_cpu_usage() {
    cpu_idle=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | sed 's/,//')
    if [ -z "$cpu_idle" ]; then
        log_error "Не удалось получить значение загрузки CPU"
        echo 0
        return
    fi
    cpu_usage=$(echo "100 - $cpu_idle" | bc)
    echo "${cpu_usage%.*}"
}

# Функция для получения загрузки оперативной памяти (в процентах)
function get_mem_usage() {
    mem_usage=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    if [ -z "$mem_usage" ]; then
        log_error "Не удалось получить значение использования памяти"
        echo 0
        return
    fi
    echo "$mem_usage"
}

# Функция, выполняющая часть задачи на сервере
function perform_task() {
    log_info "Выполняется часть задачи на сервере ($(uname -n))..."
    # Здесь разместите ваш код для обработки данных или другую логику
    sleep 5  # имитация работы
}

# Функция для передачи части задачи на основной ПК с уведомлением и расширенным логированием
function offload_task_to_pc() {
    log_info "Начало процедуры offload: попытка передать задачу на ПК $MY_PC"
    if is_pc_online; then
        log_info "Отправка задачи на ПК $MY_PC..."
        remote_output=$(ssh "$MY_PC" "bash -c 'DISPLAY=:0 notify-send \"Задача распределена\" \"Сервер распределил часть задачи на ваш ПК\" && echo Выполняется задача на удалённом ПК (\$(uname -n)); sleep 5'" 2>&1)
        exit_status=$?
        if [ $exit_status -eq 0 ]; then
            log_info "Удалённая задача выполнена успешно. Вывод: $remote_output"
        else
            log_error "Ошибка при выполнении задачи на удалённом ПК. Код ошибки: $exit_status. Вывод: $remote_output"
        fi
    else
        log_error "Передача offload не выполнена, так как ПК недоступен."
    fi
}

# Основной цикл для отслеживания нагрузки
while true; do
    cpu=$(get_cpu_usage)
    mem=$(get_mem_usage)
    log_info "Загрузка CPU: ${cpu}%"
    log_info "Загрузка RAM: ${mem}%"

    # Если хотя бы одно значение превышает порог
    if [ "$cpu" -gt "$LOAD_THRESHOLD" ] || [ "$mem" -gt "$LOAD_THRESHOLD" ]; then
        # Фиксируем время начала высокой нагрузки, если оно еще не установлено
        if [ "$high_load_start" -eq 0 ]; then
            high_load_start=$(date +%s)
            log_info "Начало высокой нагрузки зафиксировано."
        else
            current_time=$(date +%s)
            duration=$(( current_time - high_load_start ))
            log_info "Высокая нагрузка длится ${duration} секунд."
            # Если нагрузка длится дольше порога, дополнительно проверяем, все ли еще высокая
            if [ "$duration" -ge "$HIGH_LOAD_DURATION_THRESHOLD" ]; then
                # Дополнительная проверка текущей нагрузки
                cpu_current=$(get_cpu_usage)
                mem_current=$(get_mem_usage)
                if [ "$cpu_current" -gt "$LOAD_THRESHOLD" ] || [ "$mem_current" -gt "$LOAD_THRESHOLD" ]; then
                    log_info "Высокая нагрузка более ${HIGH_LOAD_DURATION_THRESHOLD} секунд и сохраняется."
                    offload_task_to_pc &
                    perform_task &
                    wait
                    log_info "Задача завершена с распределением нагрузки."
                else
                    log_info "Нагрузка снизилась до порогового значения, offload не требуется."
                    log_info "Нормальная загрузка, задача выполняется на сервере."
                    perform_task
                fi
                # Сброс таймера после выполнения
                high_load_start=0
            fi
        fi
    else
        # Если нагрузка нормальная – сбрасываем таймер, если он был установлен
        if [ "$high_load_start" -ne 0 ]; then
            log_info "Нагрузка нормализовалась, сброс таймера высокой нагрузки."
            high_load_start=0
        fi
        log_info "Нормальная загрузка, задача выполняется на сервере."
        perform_task
    fi

    log_info "Ожидание ${CHECK_INTERVAL} секунд до следующей проверки..."
    sleep "$CHECK_INTERVAL"
done
