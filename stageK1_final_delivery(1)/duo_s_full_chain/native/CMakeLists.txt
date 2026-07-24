cmake_minimum_required(VERSION 3.13)
project(duo_emg_features C)

add_library(duo_emg_features SHARED emg_features.c)
target_compile_features(duo_emg_features PRIVATE c_std_99)
target_compile_options(duo_emg_features PRIVATE -O3 -Wall -Wextra -Werror)
target_link_libraries(duo_emg_features PRIVATE m)
