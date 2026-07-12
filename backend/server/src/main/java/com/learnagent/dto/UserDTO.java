package com.learnagent.dto;

import com.learnagent.dto.User;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import lombok.EqualsAndHashCode;



@EqualsAndHashCode(callSuper = false)
@Data
@AllArgsConstructor
@NoArgsConstructor
public class UserDTO extends User implements Serializable {
    private Long id;
    private String name;
    private String image;
    private String major;
    private String grade;
    private String specialty;
}