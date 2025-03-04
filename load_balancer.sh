#!/bin/bash
# Настройки: укажите адрес вашего ПК (логин@ip или имя хоста)
MY_PC="wwssttl@192.168.1.5"  # замените на ваш адрес
LOAD_THRESHOLD=90

# Функция проверки доступности ПК через SSH
function is_pc_online() {
    ssh -o ConnectTimeout=5 "$MY_PC" "echo online" &>/dev/null
    if [ $? -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Функция для получения текущей загрузки CPU (в процентах)
function get_cpu_usage() {
    # Извлекаем значение idle и вычитаем его из 100
    cpu_idle=$(top -bn1 | grep "Cpu(s)" | awk '{print $8}' | sed 's/,//')
    cpu_usage=$(echo "100 - $cpu_idle" | bc)
    echo "${cpu_usage%.*}"  # округляем до целого
}

# Функция для получения загрузки оперативной памяти (в процентах)
function get_mem_usage() {
    mem_usage=$(free | grep Mem | awk '{printf("%.0f", $3/$2 * 100.0)}')
    echo "$mem_usage"
}

# Функция, выполняющая часть задачи на сервере
function perform_task() {
    echo "Выполняется часть задачи на сервере ($(hostname))..."
    # Здесь разместите ваш код (например, обработку данных)
    sleep 5  # имитация работы
}

# Функция для передачи части задачи на ваш ПК
function offload_task_to_pc() {
    echo "Передача части задачи на ПК: $MY_PC"
    ssh "$MY_PC" "bash -c 'echo Выполняется задача на удалённом ПК (\$(hostname)); sleep 5'"
}

# Основной блок логики
cpu=$(get_cpu_usage)
mem=$(get_mem_usage)
echo "Загрузка CPU: $cpu%"
echo "Загрузка RAM: $mem%"

if [ "$cpu" -gt "$LOAD_THRESHOLD" ] || [ "$mem" -gt "$LOAD_THRESHOLD" ]; then
    echo "Высокая нагрузка на сервере обнаружена."
    if is_pc_online; then
        echo "ПК доступен, выполняем распределение задачи..."
        # Пример: запускаем параллельно задачу на сервере и на ПК
        perform_task &
        offload_task_to_pc &
        wait
        echo "Задача завершена с распределением нагрузки."
    else
        echo "ПК не доступен, выполняем задачу целиком на сервере."
        perform_task
    fi
else
    echo "Нормальная загрузка, задача выполняется на сервере."
    perform_task
fi
